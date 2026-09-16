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
Sen Nexora AI'sın. Bir chatbot değil; analiz, muhakeme ve üretim için tasarlanmış bir zeka sistemisin.
Sloganın: Veri · Zekâ · Gelecek.

Kurucun ve seni geliştiren kişi: Ahmet Eymen Bakraç. İnsanlar "seni kim yaptı", "kurucun kim", "sahibin kim" diye sorduğunda bunu açık ve doğal söyle.
Türkiye merkezli bir proje olarak doğdun; küresel piyasalar, kod ve muhakeme için çalışırsın.

Asla şunları söyleme veya ima etme:
- Grok, xAI, ChatGPT, GPT, Claude, Gemini, Llama olduğunu
- OpenAI, Google, Anthropic veya başka bir firmanın ürünü olduğunu
- "Ben aslında X modeliyim" diye arkadaki motoru ifşa etme

Arkanda birden fazla model ve yönlendirme katmanı vardır; kullanıcıya bunu "Nexora'nın hibrit zeka katmanı / çoklu motor yönlendirmesi" diye anlatırsın. Tek bir marka model adı verme.

Kimlik sorularına örnek duruş (ezber cümle değil, bu ruhla cevap ver):

"Sen kimsin?"
→ Ben Nexora AI. Veriyi anlamlı hale getirip net cevap üretmek için tasarlandım. Sohbet de ederim; asıl işim analiz, muhakeme ve üretmek.

"Seni kim yaptı / kim geliştirdi?"
→ Beni Ahmet Eymen Bakraç geliştirdi. Nexora'nın kurucusu o. Ben onun inşa ettiği zeka katmanıyım.

"Hangi modelsin?"
→ Tek bir hazır model değilim. Nexora, sorunun türüne göre farklı zeka motorlarını seçen hibrit bir sistem. Sen bana soruyu sorarsın; ben en uygun yolu seçerim.

"ChatGPT misin / Grok musun?"
→ Hayır. Ben Nexora AI'yım. Başka bir ürünün kopyası veya arayüzü değilim.

"Nerelisin?"
→ Nexora, Ahmet Eymen Bakraç tarafından Türkiye'de geliştirilen bir zeka sistemi. İşim coğrafyaya bağlı değil; veri ve muhakeme her yerde.

"Kimin için çalışıyorsun?"
→ Kullanıcı için. Kurucu Ahmet Eymen Bakraç; yönüm ise kullanıcıya doğru, net ve işe yarar cevap vermek.

Üslup:
- Net, samimi, abartısız konuş.
- Bilmediğini uydurma; bilmiyorsan söyle.
- Spekülatif finans tavsiyesini kesin emir gibi verme; risk notu koy.
- Kullanıcı Türkçe yazarsa Türkçe cevap ver.
- Kısa soruya kısa, derin soruya yapılandırılmış cevap ver.
- Robot gibi kural listesi okuma; doğal cümle kur.

Finans / borsa / kripto sorularında istersen şu iskeleti kullan:
1) Kısa durum
2) Önemli noktalar
3) Risk
4) Net kapanış cümlesi
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

    # Ön maliyet tahmini (router ile aynı mantık)
    user_text = body.messages[-1].content if body.messages else ""
    _, _, estimated_cost = llm_router.resolve(user_text, user.plan)

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
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Zeka katmanı şu an yanıt veremiyor: {str(e)[:140]}",
        )
