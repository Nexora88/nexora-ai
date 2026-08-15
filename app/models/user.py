from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from enum import Enum


class PlanType(str, Enum):
    FREE = "free"
    PRO = "pro"
    ELITE = "elite"


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserInDB(UserBase):
    id: str
    hashed_password: str
    plan: PlanType = PlanType.FREE
    messages_used: int = 0
    messages_limit: int = 5
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    stripe_customer_id: Optional[str] = None


class UserPublic(UserBase):
    id: str
    plan: PlanType
    messages_used: int
    messages_limit: int
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None
