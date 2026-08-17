from fastapi import APIRouter, HTTPException, Header, Depends
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
    symbol: str
    question: Optional[str] = None


# Basit sembol eşleştirme
CRYPTO_MAP = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "sol": "solana",
    "solana": "solana",
    "xrp": "ripple",
    "ada": "cardano",
    "doge": "dogecoin",
    "avax": "avalanche-2",
    "dot": "polkadot",
    "matic": "matic-network",
    "link": "chainlink",
}


async def get_crypto_data(symbol: str) -> dict:
    coin_id = CRYPTO_MAP.get(symbol.lower())
    if not coin_id:
        return {}

    url = f"https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": coin_id,
        "vs_currencies": "usd,try",
        "include_24hr_change": "true",
        "include_24hr_vol": "true",
        "include_market_cap": "true",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            res = await client.get(url, params=params)
            data = res.json()
            return data.get(coin_id, {})
        except Exception:
            return {}


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
    question = body.question or f"{symbol} hakkında güncel analiz yap."

    # Gerçek veri çek
    crypto_data = await get_crypto_data(symbol)

    data_text = ""
    if crypto_data:
        price_usd = crypto_data.get("usd")
        price_try = crypto_data.get("try")
        change_24h = crypto_data.get("usd_24h_change")
        volume = crypto_data.get("usd_24h_vol")
        market_cap = crypto_data.get("usd_market_cap")

        data_text = f"""
Gerçek zamanlı veriler ({symbol}):
- Fiyat (USD): ${price_usd:,.2f} if price_usd else 'Bilinmiyor'
- Fiyat (TRY): ₺{price_try:,.2f} if price_try else 'Bilinmiyor'
- 24s Değişim: {change_24h:.2f}% if change_24h else 'Bilinmiyor'
- 24s Hacim: ${volume:,.0f} if volume else 'Bilinmiyor'
- Piyasa Değeri: ${market_cap:,.0f} if market_cap else 'Bilinmiyor'
"""

    messages = [
        {
            "role": "system",
            "content": (
                "Sen Nexora AI finans asistanısın. Sana verilen gerçek verileri kullanarak "
                "net, kısa ve temkinli analiz yap. Spekülasyon yapma. "
                "Cevabını şu yapıda ver:\n"
                "1. Kısa durum özeti\n"
                "2. Önemli noktalar\n"
                "3. Risk notu\n"
                "4. Net sonuç cümlesi\n"
                "Türkçe cevap ver."
            ),
        },
        {
            "role": "user",
            "content": f"Sembol: {symbol}\n{data_text}\nSoru: {question}",
        },
    ]

    try:
        response = await llm_router.chat(
            messages=messages,
            plan=user.plan,
            temperature=0.3,
            max_tokens=700,
        )
        content = response.choices[0].message.content

        return {
            "symbol": symbol,
            "raw_data": crypto_data,
            "analysis": content,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Analiz yapılamadı: {str(e)[:120]}")
