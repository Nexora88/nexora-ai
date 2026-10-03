from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import deduct_tokens, get_user_by_email
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.db_models import User
from app.services.weather import weather_card

router = APIRouter(prefix="/weather", tags=["weather"])
WEATHER_TOKEN_COST = 1


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token gerekli")
    payload = decode_access_token(authorization.replace("Bearer ", ""))
    if not payload:
        raise HTTPException(status_code=401, detail="Geçersiz oturum")
    user = await get_user_by_email(payload.get("email"), db)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı yok")
    return user


@router.get("/card")
async def get_weather_card(
    city: str = Query(..., min_length=2, description="İstanbul, Ankara, London…"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.tokens < WEATHER_TOKEN_COST:
        raise HTTPException(status_code=402, detail="Token yetersiz")

    card = await weather_card(city.strip())
    if not card.get("ok"):
        raise HTTPException(status_code=404, detail=card.get("error") or "Bulunamadı")

    remaining = await deduct_tokens(user.email, WEATHER_TOKEN_COST, db)
    return {
        **card,
        "token_cost": WEATHER_TOKEN_COST,
        "tokens": remaining,
    }
