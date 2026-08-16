from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
import httpx

from app.core.database import get_db
from app.core.security import decode_access_token
from app.api.auth import get_user_by_email
from app.services.llm_router import llm_router
from app.models.user import PlanType

router = APIRouter(prefix="/market", tags=["market"])


class MarketRequest(BaseModel):
    symbol: str  # Örnek: BTC, THYAO, AAPL, EURUSD
    question: Optional[str] = None


@router.post("/analyze")
async def analyze_market(
    body: MarketRequest,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token gerekli")

    token = authorization.replace("Bearer ", "")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Geçersiz token")

    email = payload.get("email")
    user = await get_user_by_email(email, db)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

    symbol = body.symbol.upper().strip()
    question = body.question or f"{symbol} hakkında kısa analiz yap, güncel durum nedir?"

    # Basit prompt ile LLM'e soruyoruz (ileride gerçek veri API'si ekleriz)
    messages = [
        {
            "role": "system",
            "content": (
                "Sen Nexora AI finans asistanısın. Borsa, kripto ve forex konusunda "
                "net, kısa ve yararlı analizler yap. Spekülasyon yapma, bilgilendir. "
                "Türkçe cevap ver."
            ),
        },
        {
            "role": "user",
            "content": f"Sembol: {symbol}\nSoru: {question}",
        },
    ]

    try:
        response = await llm_router.chat(
            messages=messages,
            plan=user.plan,
            temperature=0.4,
            max_tokens=800,
        )
        content = response.choices[0].message.content
        return {
            "symbol": symbol,
            "analysis": content,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Analiz yapılamadı: {str(e)[:100]}")
