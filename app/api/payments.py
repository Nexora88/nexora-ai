from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import decode_access_token
from app.api.auth import get_user_by_email
from app.services.stripe_service import create_checkout_session
from app.models.user import PlanType

router = APIRouter(prefix="/payments", tags=["payments"])
settings = get_settings()


class CheckoutRequest(BaseModel):
    plan: str  # "pro" veya "elite"


@router.post("/create-checkout")
async def create_checkout(
    body: CheckoutRequest,
    authorization: str = None,
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

    if body.plan == "pro":
        price_id = settings.STRIPE_PRO_PRICE_ID
    elif body.plan == "elite":
        price_id = settings.STRIPE_ELITE_PRICE_ID
    else:
        raise HTTPException(status_code=400, detail="Geçersiz plan")

    if not price_id:
        raise HTTPException(status_code=500, detail="Stripe Price ID ayarlanmamış")

    # Geçici success/cancel url (ileride frontend adresi gelecek)
    success_url = "http://localhost:3000/success?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = "http://localhost:3000/cancel"

    session = create_checkout_session(
    customer_email=user.email,
    price_id=price_id,
    plan=body.plan,
    success_url=success_url,
    cancel_url=cancel_url,
    )

    return {"checkout_url": session.url}
