import stripe
from app.core.config import get_settings

settings = get_settings()
stripe.api_key = settings.STRIPE_SECRET_KEY


def create_checkout_session(customer_email: str, price_id: str, success_url: str, cancel_url: str):
    session = stripe.checkout.Session.create(
        customer_email=customer_email,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return session


def create_customer(email: str, name: str = None):
    customer = stripe.Customer.create(email=email, name=name)
    return customer
