"""
Nexora AI — Media attach layer
Dosya / görsel / ses yükleme + token
"""
from __future__ import annotations

import base64
import re
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import deduct_tokens, get_user_by_email
from app.core.database import get_db
from app.core.security import decode_access_token
from app.services.llm_router import llm_router

router = APIRouter(prefix="/media", tags=["media"])

# Ek token fiyatları
COST_IMAGE = 2
COST_FILE = 2
COST_AUDIO = 3
COST_VIDEO = 4

MAX_BYTES = 8 * 1024 * 1024  # 8 MB

ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_FILE = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/pdf",
}
ALLOWED_AUDIO = {"audio/mpeg", "audio/wav", "audio/webm", "audio/mp4", "audio/x-wav"}
ALLOWED_VIDEO = {"video/mp4", "video/webm"}


class MediaResponse(BaseModel):
    kind: str
    filename: str
    token_cost: int
    tokens: int
    analysis: str
    model_used: str = "nexora-media"
    note: str = ""


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token gerekli")
    payload = decode_access_token(authorization.replace("Bearer ", ""))
    if not payload:
        raise HTTPException(status_code=401, detail="Geçersiz token")
    user = await get_user_by_email(payload.get("email"), db)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    return user


def detect_kind(content_type: str, filename: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    name = (filename or "").lower()
    if ct in ALLOWED_IMAGE or name.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return "image"
    if ct in ALLOWED_AUDIO or name.endswith((".mp3", ".wav", ".webm", ".m4a")):
        return "audio"
    if ct in ALLOWED_VIDEO or name.endswith((".mp4", ".webm", ".mov")):
        return "video"
    if ct in ALLOWED_FILE or name.endswith((".txt", ".md", ".csv", ".json", ".pdf")):
        return "file"
    return "unknown"


def cost_for(kind: str) -> int:
    return {
        "image": COST_IMAGE,
        "file": COST_FILE,
        "audio": COST_AUDIO,
        "video": COST_VIDEO,
    }.get(kind, 2)


async def extract_text_file(data: bytes, filename: str, content_type: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf") or content_type == "application/pdf":
        try:
            from pypdf import PdfReader
            import io

            reader = PdfReader(io.BytesIO(data))
            parts = []
            for page in reader.pages[:15]:
                parts.append(page.extract_text() or "")
            text = "\n".join(parts).strip()
            return text[:12000] if text else "[PDF metni çıkarılamadı]"
        except Exception:
            return "[PDF okunamadı — pypdf gerekli veya dosya korumalı]"
    try:
        return data.decode("utf-8", errors="ignore")[:12000]
    except Exception:
        return "[Dosya metne çevrilemedi]"


MEDIA_SYSTEM = """
Sen Nexora AI medya katmanısın. Kullanıcının yüklediği içeriği analiz et.
Türkçe, net, abartısız cevap ver. Grok/ChatGPT olduğunu söyleme.
Yatırım emri verme. Küfür kullanma.
Görselde net göremediğin şeyi uydurma.
""".strip()


@router.post("/analyze", response_model=MediaResponse)
async def analyze_media(
    file: UploadFile = File(...),
    prompt: str = Form("Bu içeriği analiz et."),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(authorization, db)

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Boş dosya")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="Dosya en fazla 8 MB olabilir")

    kind = detect_kind(file.content_type or "", file.filename or "")
    if kind == "unknown":
        raise HTTPException(
            status_code=400,
            detail="Desteklenmeyen tür. Görsel, metin/PDF, ses veya video dene.",
        )
    if kind == "video":
        raise HTTPException(
            status_code=400,
            detail=f"Video analizi yakında. Planlanan maliyet: +{COST_VIDEO} token.",
        )

    cost = cost_for(kind)
    if user.tokens < cost:
        raise HTTPException(
            status_code=402,
            detail=f"Bu yükleme {cost} token. Kalan: {user.tokens}",
        )

    analysis = ""
    model_used = "nexora-media"
    note = ""

    try:
        if kind == "file":
            text = await extract_text_file(data, file.filename or "file", file.content_type or "")
            messages = [
                {"role": "system", "content": MEDIA_SYSTEM},
                {
                    "role": "user",
                    "content": f"Dosya: {file.filename}\n\nİçerik:\n{text}\n\nİstek: {prompt}",
                },
            ]
            result = await llm_router.chat(
                messages=messages,
                plan=user.plan,
                temperature=0.3,
                max_tokens=1000,
            )
            analysis = result.response.choices[0].message.content
            model_used = result.model_used
            note = "Metin/PDF analizi"

        elif kind == "image":
            b64 = base64.b64encode(data).decode("ascii")
            mime = (file.content_type or "image/jpeg").split(";")[0]
            # Vision denemesi — model vision desteklemiyorsa fallback metin
            vision_messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"{prompt}\nDosya: {file.filename}"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                    ],
                }
            ]
            try:
                from litellm import acompletion

                # Ücretsiz/uygun vision model yoksa bu blok hata verir → fallback
                resp = await acompletion(
                    model="groq/llama-3.2-11b-vision-preview",
                    messages=vision_messages,
                    max_tokens=800,
                )
                analysis = resp.choices[0].message.content
                model_used = "groq/llama-3.2-11b-vision-preview"
                note = "Görsel analizi (vision)"
            except Exception:
                # Fallback: vision yoksa dürüst cevap + token yine düşer (deneme maliyeti)
                messages = [
                    {"role": "system", "content": MEDIA_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Kullanıcı görsel yükledi: {file.filename} ({mime}, {len(data)} byte). "
                            f"İstek: {prompt}\n"
                            "Şu an vision motoru bu ortamda yanıt vermedi. "
                            "Kullanıcıya kısa, dürüst açıkla; yine de ne yapılabileceğini söyle."
                        ),
                    },
                ]
                result = await llm_router.chat(
                    messages=messages,
                    plan=user.plan,
                    temperature=0.3,
                    max_tokens=400,
                )
                analysis = result.response.choices[0].message.content
                model_used = result.model_used
                note = "Görsel: vision yedek mod"

        elif kind == "audio":
            note = "Ses kabul edildi — transkripsiyon API Faz 2"
            analysis = (
                f"Ses dosyan alındı: **{file.filename}** ({len(data)} byte).\n\n"
                f"Transkripsiyon motoru henüz bağlı değil. "
                f"Bu işlem için **{cost} token** ayrıldı; metne çeviri bir sonraki sürümde açılacak.\n\n"
                f"İsteğin: {prompt}"
            )
            model_used = "nexora-media-audio-stub"

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Medya işlenemedi: {str(e)[:120]}")

    remaining = await deduct_tokens(user.email, cost, db)

    return MediaResponse(
        kind=kind,
        filename=file.filename or "upload",
        token_cost=cost,
        tokens=remaining,
        analysis=analysis,
        model_used=model_used,
        note=note,
      )
