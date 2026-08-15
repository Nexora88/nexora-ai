from fastapi import APIRouter, HTTPException, status
from datetime import datetime, timezone
import uuid

from app.models.user import UserCreate, UserLogin, UserPublic, Token, PlanType
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

# Geçici hafıza (daha sonra gerçek veritabanına geçeceğiz)
_users_db: dict = {}


@router.post("/register", response_model=UserPublic)
async def register(user_in: UserCreate):
    if user_in.email in _users_db:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    user = {
        "id": user_id,
        "email": user_in.email,
        "full_name": user_in.full_name,
        "hashed_password": get_password_hash(user_in.password),
        "plan": PlanType.FREE,
        "messages_used": 0,
        "messages_limit": settings.FREE_MESSAGES_LIMIT,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
        "stripe_customer_id": None,
    }
    _users_db[user_in.email] = user

    return UserPublic(
        id=user["id"],
        email=user["email"],
        full_name=user["full_name"],
        plan=user["plan"],
        messages_used=user["messages_used"],
        messages_limit=user["messages_limit"],
        is_active=user["is_active"],
        created_at=user["created_at"],
    )


@router.post("/login", response_model=Token)
async def login(user_in: UserLogin):
    user = _users_db.get(user_in.email)
    if not user or not verify_password(user_in.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token = create_access_token(data={"sub": user["id"], "email": user["email"]})
    return Token(access_token=access_token)


@router.get("/me", response_model=UserPublic)
async def get_me(token: str):
    from app.core.security import decode_access_token

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    email = payload.get("email")
    user = _users_db.get(email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserPublic(
        id=user["id"],
        email=user["email"],
        full_name=user["full_name"],
        plan=user["plan"],
        messages_used=user["messages_used"],
        messages_limit=user["messages_limit"],
        is_active=user["is_active"],
        created_at=user["created_at"],
    )


def get_user_by_email(email: str):
    return _users_db.get(email)


def increment_usage(email: str):
    user = _users_db.get(email)
    if user:
        user["messages_used"] += 1
        user["updated_at"] = datetime.now(timezone.utc)
