"""
Nexora AI — Market Analysis Layer
Canlı veri + hibrit router + token ekonomisi
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import deduct_tokens, get_user_by_email
from app.core.database import get_db
from app.core.security import decode_access_token
from app.services.llm_router import llm_router

router = APIRouter(prefix="/market", tags=["market"])

# Analiz her zaman finans sınıfı → 3 token
MARKET_TOKEN_COST = 3

CRYPTO_MAP: Dict[str, str] = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "sol": "solana",
    "solana": "solana",
    "xrp": "ripple",
    "ripple": "ripple",
    "ada": "cardano",
    "cardano": "cardano",
    "doge": "dogecoin",
    "dogecoin": "dogecoin",
    "avax": "avalanche-2",
    "dot": "polkadot",
    "matic": "matic-network",
    "link": "chainlink",
    "bnb": "binancecoin",
    "ltc": "litecoin",
    "uni": "uniswap",
    "atom": "cosmos",
    "near": "near",
    "apt": "aptos",
    "arb": "arbitrum",
    "op": "optimism",
    "pepe": "pepe",
    "shib": "shiba-inu",
}

# BIST / hisse — veri kaynağı yoksa LLM temkinli yorumlar
EQUITY_HINTS = {
    "thyao", "aselsan", "garen", "akbnk", "ykbnk", "eregl", "sahol",
    "bist", "xu100", "sise", "kchol", "tuprs", "ase", "froto",
}


class MarketRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32)
    question: Optional[str] = None


class MarketResponse(BaseModel):
    symbol: str
    asset_class: str
    raw_data: Dict[str, Any]
    analysis: str
    model_used: str
    query_type: str = "finance"
    token_cost: int
    tokens: int
    latency_ms: int = 0


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token gerekli")
    payload = decode_access_token(authorization.replace("Bearer ", ""))
    if not payload:
        raise HTTPException(status_code=401, detail="Geçersiz token")
    email = payload.get("email")
    user = await get_user_by_email(email, db)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    return user


def fmt_num(v: Any, prefix: str = "", digits: int = 2) -> str:
    try:
        if v is None:
            return "—"
        n = float(v)
        if abs(n) >= 1_000_000_000:
            return f"{prefix}{n/1_000_000_000:.2f}B"
        if abs(n) >= 1_000_000:
            return f"{prefix}{n/1_000_000:.2f}M"
        return f"{prefix}{n:,.{digits}f}"
    except Exception:
        return "—"


async def fetch_coingecko(symbol: str) -> Dict[str, Any]:
    coin_id = CRYPTO_MAP.get(symbol.lower().strip())
    if not coin_id:
        return {}

    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": coin_id,
        "vs_currencies": "usd,try",
        "include_24hr_change": "true",
        "include_24hr_vol": "true",
        "include_market_cap": "true",
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.get(url, params=params)
            res.raise_for_status()
            data = res.json().get(coin_id) or {}
            return {
                "provider": "coingecko",
                "coin_id": coin_id,
                "price_usd": data.get("usd"),
                "price_try": data.get("try"),
                "change_24h_pct": data.get("usd_24h_change"),
                "volume_24h_usd": data.get("usd_24h_vol"),
                "market_cap_usd": data.get("usd_market_cap"),
            }
    except Exception:
        return {"provider": "coingecko", "error": "veri_alinamadi"}


def classify_asset(symbol: str) -> str:
    s = symbol.lower().strip()
    if s in CRYPTO_MAP or s in CRYPTO_MAP.values():
        return "crypto"
    if s in EQUITY_HINTS or s.endswith(".is"):
        return "equity"
    # 2–5 harf hisse gibi
    if 2 <= len(s) <= 6 and s.isalpha():
        return "equity_or_unknown"
    return "unknown"


def build_data_brief(symbol: str, raw: Dict[str, Any], asset_class: str) -> str:
    lines = [f"Sembol: {symbol}", f"Varlık sınıfı (tahmini): {asset_class}"]
    if raw.get("price_usd") is not None:
        lines.append(f"Fiyat USD: {fmt_num(raw.get('price_usd'), '$')}")
        lines.append(f"Fiyat TRY: {fmt_num(raw.get('price_try'), '₺')}")
        ch = raw.get("change_24h_pct")
        lines.append(f"24s değişim: {fmt_num(ch, digits=2)}%")
        lines.append(f"24s hacim: {fmt_num(raw.get('volume_24h_usd'), '$', 0)}")
        lines.append(f"Piyasa değeri: {fmt_num(raw.get('market_cap_usd'), '$', 0)}")
        lines.append("Kaynak: CoinGecko (gecikmeli / ücretsiz katman)")
    elif asset_class.startswith("equity"):
        lines.append(
            "Canlı hisse kotasyonu bu endpointte yok. "
            "Genel çerçeve, risk ve temkinli yorum üret; kesin fiyat uydurma."
        )
    else:
        lines.append("Anlık fiyat verisi yok. Spekülatif kesin rakam üretme.")
    return "\n".join(lines)


MARKET_SYSTEM = """
Sen Nexora AI piyasa katmanısın. Türkiye'de geliştirilmiş hibrit zeka sisteminin finans modülüsün.
Kurucu bağlamı: Nexora / Ahmet Eymen Bakraç. Grok veya ChatGPT olduğunu söyleme.

Görevin: verilen veriyi kullanarak temkinli, net, profesyonel analiz.
- Veri varsa veriye dayan.
- Veri yoksa uydurma fiyat yazma; belirsizliği söyle.
- Yatırım tavsiyesi gibi emir kipi kullanma ("mutlaka al/sat" yok).
- Risk notu koy.
- Türkçe yaz.

Cevap iskeleti:
1) Kısa durum
2) Önemli noktalar (madde)
3) Riskler
4) Net kapanış (tek cümle, temkinli)
""".strip()


@router.post("/analyze", response_model=MarketResponse)
async def analyze_market(
    body: MarketRequest,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(authorization, db)

    if user.tokens <= 0:
        raise HTTPException(
            status_code=402,
            detail="Token hakkın bitti. Mağazadan token al veya Pro / Elite'e geç.",
        )
    if user.tokens < MARKET_TOKEN_COST:
        raise HTTPException(
            status_code=402,
            detail=f"Piyasa analizi {MARKET_TOKEN_COST} token. Kalan: {user.tokens}",
        )

    symbol = body.symbol.upper().strip()
    asset_class = classify_asset(symbol)
    raw = await fetch_coingecko(symbol)
    brief = build_data_brief(symbol, raw, asset_class)
    question = (body.question or f"{symbol} için güncel, temkinli piyasa analizi.").strip()

    messages = [
        {"role": "system", "content": MARKET_SYSTEM},
        {
            "role": "user",
            "content": f"{brief}\n\nKullanıcı sorusu:\n{question}",
        },
    ]

    try:
        result = await llm_router.chat(
            messages=messages,
            plan=user.plan,
            temperature=0.25,
            max_tokens=900,
            stream=False,
        )
        content = result.response.choices[0].message.content
        # Piyasa her zaman finans maliyeti
        cost = MARKET_TOKEN_COST
        remaining = await deduct_tokens(user.email, cost, db)

        return MarketResponse(
            symbol=symbol,
            asset_class=asset_class,
            raw_data=raw,
            analysis=content,
            model_used=result.model_used,
            query_type="finance",
            token_cost=cost,
            tokens=remaining,
            latency_ms=getattr(result, "latency_ms", 0) or 0,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Piyasa katmanı yanıt veremedi: {str(e)[:140]}",
        )


@router.get("/symbols")
async def list_known_symbols():
    """Desteklenen kripto kısaltmaları (bilgi amaçlı)."""
    return {
        "crypto": sorted(set(CRYPTO_MAP.keys())),
        "note": "Hisse sembolleri de kabul edilir; canlı kotasyon kripto odaklıdır.",
    }
