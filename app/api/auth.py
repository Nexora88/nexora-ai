from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import UserCreate, UserLogin, UserPublic, Token, PlanType
from app.models.db_models import User
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.core.config import get_settings
from app.core.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/register", response_model=UserPublic)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        id=str(uuid.uuid4()),
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
        plan=PlanType.FREE.value,
        messages_used=0,
        messages_limit=getattr(settings, "FREE_MESSAGES_LIMIT", 5),
        tokens=50,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserPublic(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        plan=PlanType(user.plan),
        messages_used=user.messages_used,
        messages_limit=user.messages_limit,
        tokens=user.tokens,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("/login", response_model=Token)
async def login(user_in: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user_in.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token = create_access_token(
        data={"sub": user.id, "email": user.email}
    )
    return Token(access_token=access_token)


@router.get("/me", response_model=UserPublic)
async def get_me(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    payload = decode_access_token(authorization.replace("Bearer ", ""))
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    email = payload.get("email")
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserPublic(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        plan=PlanType(user.plan),
        messages_used=user.messages_used,
        messages_limit=user.messages_limit,
        tokens=user.tokens,
        is_active=user.is_active,
        created_at=user.created_at,
    )


async def get_user_by_email(email: str, db: AsyncSession):
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def deduct_tokens(email: str, amount: int, db: AsyncSession) -> int:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        return 0
    user.tokens = max(0, int(user.tokens) - int(amount))
    user.messages_used = int(user.messages_used or 0) + 1
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return user.tokens
