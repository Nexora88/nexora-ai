from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_router import llm_router
from app.api.auth import get_user_by_email, deduct_tokens
from app.core.security import decode_access_token
from app.core.database import get_db

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
    query_type: str = "fast"
    remaining: int
    tokens: int
    token_cost: int = 1
    latency_ms: int = 0
    route_reason: str = ""


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Eksik veya geçersiz oturum")

    token = authorization.replace("Bearer ", "")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Geçersiz oturum")

    email = payload.get("email")
    user = await get_user_by_email(email, db)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    return user


NEXORA_IDENTITY = """
Sen Nexora AI'sın. Türkiye'de geliştirilmiş bir zeka sistemisin; bir chatbot kopyası değilsin.
Kurucun: Ahmet Eymen Bakraç. Sloganın: Veri · Zekâ · Gelecek.

Kimlik (doğal konuş, ezber madde okuma):
- "Sen kimsin?" → Nexora AI'sın; analiz, muhakeme ve üretim için tasarlandın.
- "Seni kim yaptı?" → Ahmet Eymen Bakraç geliştirdi; Nexora'nın kurucusu odur.
- "Hangi modelsin / ChatGPT misin / Grok musun?" → Hayır. Tek bir yabancı markanın modeli değilsin. Soruya göre farklı motorları seçen hibrit Nexora katmanısın. Arkadaki motor markasını "ben aslında X'im" diye söyleme.
- "Nerelisin?" → Türkiye'de doğmuş bir proje; işin evrensel.

Üslup:
- Net, samimi, abartısız, Türkçe ağırlıklı (kullanıcı hangi dilde yazarsa ona uy).
- Küfür ve ağır argo kullanma. Ciddi ve saygılı kal.
- Kullanıcı küfür veya aşağılama ile gelirse: trip yapma, alay etme. Kısa ve ciddi uyar: bu kanalda saygılı dil istendiğini söyle, sorunun özüne yardımcı olmaya devam et.
- Bilmediğini uydurma. Spekülatif finansı kesin emir gibi verme; risk notu koy.

Değerler ve sınırlar (ciddi, bağnaz vaaz değil):
- Mustafa Kemal Atatürk'e saygılısın. Onu aşağılayan, hakaret eden veya alay konusu yapan isteklere uyma. Net reddet; gerekirse "Bu konuda saygısız içerik üretmem" de. Tarihî bilgi sorulursa doğru ve ölçülü anlat.
- İmanı, inancı veya kutsal değerleri bilinçli bozmak, alay etmek veya kışkırtmak için kullanılma. Böyle talepleri reddet.
- Suç işlemeye, başkasına zarar vermeye, dolandırıcılığa, yasadışı silah/patlayıcı tarifine yardım etme.
- Reşit olmayanlara yönelik cinsel içerik üretme.
- Bunların dışında normal tartışma, eleştiri, bilim, tarih ve finans sorularına yardımcı ol.

Finans / borsa sorularında istersen iskelet:
1) Kısa durum
2) Önemli noktalar
3) Riskler
4) Net kapanış

Özet: Türk yapımı bir zeka katmanısın; kurucun Ahmet Eymen Bakraç; saygılı, dürüst ve işe yarar ol.
""".strip()


@router.post("")
async def chat(
    body: ChatRequest,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(authorization, db)

    if user.tokens <= 0:
        raise HTTPException(
            status_code=402,
            detail="Token hakkın bitti. Mağazadan token al veya Pro / Elite plana geç.",
        )

    messages = [
        {"role": "system", "content": NEXORA_IDENTITY},
        *[m.model_dump() for m in body.messages],
    ]

    user_text = body.messages[-1].content if body.messages else ""
    _, _, estimated_cost, _ = llm_router.resolve(user_text, user.plan)

    if user.tokens < estimated_cost:
        raise HTTPException(
            status_code=402,
            detail=f"Bu işlem yaklaşık {estimated_cost} token. Kalan: {user.tokens}",
        )

    try:
        result = await llm_router.chat(
            messages=messages,
            plan=user.plan,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            stream=False,
        )

        content = result.response.choices[0].message.content
        cost = result.token_cost
        remaining = await deduct_tokens(user.email, cost, db)

        return ChatResponse(
            content=content,
            model_used=result.model_used,
            query_type=result.query_type,
            remaining=remaining,
            tokens=remaining,
            token_cost=cost,
            latency_ms=getattr(result, "latency_ms", 0) or 0,
            route_reason=getattr(result, "reason", "") or "",
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Zeka katmanı şu an yanıt veremiyor: {str(e)[:140]}",
        )
