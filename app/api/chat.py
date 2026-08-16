from fastapi import APIRouter, HTTPException, status, Header, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_router import llm_router
from app.services.usage import can_send_message, remaining_messages
from app.api.auth import get_user_by_email, increment_usage
from app.core.security import decode_access_token
from app.core.database import get_db
from app.models.user import PlanType

router = APIRouter(prefix="/chat", tags=["chat"])


class Message(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False


class ChatResponse(BaseModel):
    content: str
    model_used: str = "nexora-router"
    remaining: int


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = authorization.replace("Bearer ", "")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    email = payload.get("email")
    user = await get_user_by_email(email, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("")
async def chat(
    body: ChatRequest,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(authorization, db)

    plan = PlanType(user.plan)

    if not can_send_message(user.messages_used, plan):
        raise HTTPException(
            status_code=402,
            detail=f"Mesaj hakkın doldu. Plan: {plan.value}. Pro veya Elite'e yükselt.",
        )

    system_prompt = {
        "role": "system",
        "content": (
            "Sen Nexora AI'sın. Veri, Zekâ ve Gelecek odaklı, yardımcı, net ve samimi bir asistanısın. "
            "Türkçe veya kullanıcının dilinde cevap ver. Kod, ödev, borsa ve genel konularda güçlü yardım et. "
            "Gereksiz uzun yazma, doğru ve faydalı ol."
        ),
    }

    messages = [system_prompt] + [m.model_dump() for m in body.messages]

    try:
        if body.stream:
            async def generate():
                async for chunk in llm_router.stream_chat(
                    messages=messages,
                    plan=plan.value,
                    temperature=body.temperature,
                    max_tokens=body.max_tokens,
                ):
                    yield chunk
                await increment_usage(user.email, db)

            return StreamingResponse(generate(), media_type="text/plain")

        response = await llm_router.chat(
            messages=messages,
            plan=plan.value,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            stream=False,
        )

        content = response.choices[0].message.content
        await increment_usage(user.email, db)

        remaining = remaining_messages(user.messages_used + 1, plan)

        return ChatResponse(
            content=content,
            remaining=remaining,
        )

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Model servisi şu an kullanılamıyor: {str(e)[:100]}",
        )
