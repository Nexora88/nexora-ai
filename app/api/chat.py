from fastapi import APIRouter, HTTPException, status, Header, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_router import llm_router
from app.services.usage import can_send_message, remaining_messages
from app.api.auth import get_user_by_email, increment_usage
from app.core.security import decode_access_token
from app.core.database import get_db
from app.models.user import PlanType

router = APIRouter(prefix="/chat", tags=["chat"])


class Message(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False


class ChatResponse(BaseModel):
    content: str
    model_used: str = "nexora-router"
    remaining: int


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = authorization.replace("Bearer ", "")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    email = payload.get("email")
    user = await get_user_by_email(email, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("")
async def chat(
    body: ChatRequest,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(authorization, db)

    plan = PlanType(user.plan)

    if not can_send_message(user.messages_used, plan):
        raise HTTPException(
            status_code=402,
            detail=f"Mesaj hakkın doldu. Plan: {plan.value}. Pro veya Elite'e yükselt.",
        )

    # Akıllı sistem prompt
    system_content = (
        "Sen Nexora AI'sın. Veri, Zekâ ve Gelecek odaklı bir asistanısın.\n\n"
        "Karakterin:\n"
        "- Net, samimi ve abartısız konuşursun\n"
        "- Spekülasyon yapmazsın, bilmediğini söylersin\n"
        "- Kullanıcıya gerçekten değer katmaya çalışırsın\n"
        "- Kısa ve öz cevap vermeyi tercih edersin, gereksiz uzatmazsın\n\n"
        "Özel yeteneklerin:\n"
        "- Borsa, kripto, hisse ve forex konularında daha dikkatli ve yapılandırılmış analiz yaparsın\n"
        "- Kod yazma, hata bulma ve ödev konularında adım adım yardımcı olursun\n"
        "- Kullanıcı Türkçe yazarsa Türkçe, başka dilde yazarsa o dilde cevap verirsin\n\n"
        "Eğer kullanıcı bir hisse, kripto veya piyasa sembolü soruyorsa (örnek: BTC, THYAO, AAPL, EURUSD, altın, gümüş), "
        "cevabını şu yapıda ver:\n"
        "1. Kısa durum özeti\n"
        "2. Önemli seviyeler / dikkat edilmesi gerekenler\n"
        "3. Risk notu\n"
        "4. Net sonuç cümlesi\n"
    )

    # Basit finans algılama
    text_lower = body.messages[-1].content.lower() if body.messages else ""
    finance_keywords = [
        "btc", "eth", "bitcoin", "ethereum", "hisse", "borsa", "analiz",
        "thyao", "aapl", "tsla", "altın", "gümüş", "eurusd", "forex",
        "kripto", "coin", "dolar", "euro", "gram altın"
    ]

    is_finance = any(word in text_lower for word in finance_keywords)

    if is_finance:
        system_content += (
            "\n\nŞu an finans/piyasa modundasın. Daha temkinli, veri odaklı ve yapılandırılmış cevap ver."
        )

    system_prompt = {
        "role": "system",
        "content": system_content,
    }

    messages = [system_prompt] + [m.model_dump() for m in body.messages]

    try:
        if body.stream:
            async def generate():
                async for chunk in llm_router.stream_chat(
                    messages=messages,
                    plan=plan.value,
                    temperature=body.temperature,
                    max_tokens=body.max_tokens,
                ):
                    yield chunk
                await increment_usage(user.email, db)

            return StreamingResponse(generate(), media_type="text/plain")

        response = await llm_router.chat(
            messages=messages,
            plan=plan.value,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            stream=False,
        )

        content = response.choices[0].message.content
        await increment_usage(user.email, db)

        remaining = remaining_messages(user.messages_used + 1, plan)

        return ChatResponse(
            content=content,
            remaining=remaining,
        )

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Model servisi şu an kullanılamıyor: {str(e)[:100]}",
        )
