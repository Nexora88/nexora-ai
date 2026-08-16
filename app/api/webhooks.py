from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import stripe

from app.core.config import get_settings
from app.core.database import get_db
from app.models.db_models import User
from app.models.user import PlanType

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
settings = get_settings()
stripe.api_key = settings.STRIPE_SECRET_KEY


@router.post("/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session.get("customer_email")
        price_id = session["display_items"][0]["price"]["id"] if session.get("display_items") else None

        # Basit eşleme
        new_plan = PlanType.FREE.value
        new_limit = settings.FREE_MESSAGES_LIMIT

        if price_id == settings.STRIPE_PRO_PRICE_ID:
            new_plan = PlanType.PRO.value
            new_limit = settings.PRO_MESSAGES_LIMIT
        elif price_id == settings.STRIPE_ELITE_PRICE_ID:
            new_plan = PlanType.ELITE.value
            new_limit = settings.ELITE_MESSAGES_LIMIT

        if customer_email:
            result = await db.execute(select(User).where(User.email == customer_email))
            user = result.scalar_one_or_none()
            if user:
                user.plan = new_plan
                user.messages_limit = new_limit
                user.messages_used = 0  # Yeni plana geçince hakkı sıfırla
                await db.commit()

    return {"status": "success"}
