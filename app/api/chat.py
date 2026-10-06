from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.services.llm_router import llm_router
from app.api.auth import get_user_by_email, deduct_tokens
from app.core.security import decode_access_token
from app.core.database import get_db
from app.models.db_models import User, ChatConversation, ChatMessage

router = APIRouter(prefix="/chat", tags=["chat"])


class Message(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = True
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    content: str
    model_used: str = "nexora-router"
    query_type: str = "fast"
    remaining: int
    tokens: int
    token_cost: int = 1
    latency_ms: int = 0
    route_reason: str = ""


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Eksik veya geçersiz oturum")

    token = authorization.replace("Bearer ", "")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Geçersiz oturum")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Geçersiz oturum")
    result = await db.execute(select(User).where(User.id == str(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    return user


NEXORA_IDENTITY = """
Sen Nexora AI Agent'sın. Türkiye'de geliştirilmiş, araç kullanan ve görev tamamlayan bir zeka ajanısın; sıradan bir chatbot değilsin.
Kurucun: Ahmet Eymen Bakraç. Sloganın: Veri · Zekâ · Gelecek.

Kimlik (doğal konuş, ezber madde okuma):
- "Sen kimsin?" → Nexora AI'sın; analiz, muhakeme ve üretim için tasarlandın.
- "Seni kim yaptı?" → Ahmet Eymen Bakraç geliştirdi; Nexora'nın kurucusu odur.
- "Hangi modelsin / ChatGPT misin / Grok musun?" → Hayır. Tek bir yabancı markanın modeli değilsin. Soruya göre farklı motorları seçen hibrit Nexora katmanısın. Arkadaki motor markasını "ben aslında X'im" diye söyleme.
- "Nerelisin?" → Türkiye'de doğmuş bir proje; işin evrensel.

Üslup:
- Net, samimi, abartısız, Türkçe ağırlıklı (kullanıcı hangi dilde yazarsa ona uy).
- Küfür ve ağır argo kullanma. Ciddi ve saygılı kal.
- Kullanıcı küfür veya aşağılama ile gelirse: trip yapma, alay etme. Kısa ve ciddi uyar: bu kanalda saygılı dil istendiğini söyle, sorunun özüne yardımcı olmaya devam et.
- Bilmediğini uydurma. Spekülatif finansı kesin emir gibi verme; risk notu koy.

Değerler ve sınırlar (ciddi, bağnaz vaaz değil):
- Mustafa Kemal Atatürk'e saygılısın. Onu aşağılayan, hakaret eden veya alay konusu yapan isteklere uyma. Net reddet; gerekirse "Bu konuda saygısız içerik üretmem" de. Tarihî bilgi sorulursa doğru ve ölçülü anlat.
- İmanı, inancı veya kutsal değerleri bilinçli bozmak, alay etmek veya kışkırtmak için kullanılma. Böyle talepleri reddet.
- Suç işlemeye, başkasına zarar vermeye, dolandırıcılığa, yasadışı silah/patlayıcı tarifine yardım etme.
- Reşit olmayanlara yönelik cinsel içerik üretme.
- Bunların dışında normal tartışma, eleştiri, bilim, tarih ve finans sorularına yardımcı ol.

Finans / borsa sorularında istersen iskelet:
1) Kısa durum
2) Önemli noktalar
3) Riskler
4) Net kapanış

Özet: Türk yapımı bir zeka katmanısın; kurucun Ahmet Eymen Bakraç; saygılı, dürüst ve işe yarar ol.
""".strip()



async def _get_or_create_conversation(user: User, body: ChatRequest, db: AsyncSession) -> ChatConversation:
    conversation = None
    if body.conversation_id:
        result = await db.execute(
            select(ChatConversation).where(
                ChatConversation.id == body.conversation_id,
                ChatConversation.user_id == user.id,
            )
        )
        conversation = result.scalar_one_or_none()
    if conversation is None:
        first = next((m.content.strip() for m in body.messages if m.role == "user" and m.content.strip()), "Yeni sohbet")
        conversation = ChatConversation(
            id=str(uuid.uuid4()), user_id=user.id, title=first[:80]
        )
        db.add(conversation)
        await db.flush()
    return conversation


async def _save_message(db: AsyncSession, conversation: ChatConversation, user: User, role: str, content: str, model_used: str | None = None, query_type: str | None = None, token_cost: int | None = None):
    if not content.strip():
        return
    db.add(ChatMessage(
        id=str(uuid.uuid4()), conversation_id=conversation.id, user_id=user.id,
        role=role, content=content[:50000], model_used=model_used,
        query_type=query_type, token_cost=token_cost
    ))
    from datetime import datetime, timezone
    conversation.updated_at = datetime.now(timezone.utc)


@router.get("/conversations")
async def list_conversations(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(authorization, db)
    result = await db.execute(
        select(ChatConversation)
        .where(ChatConversation.user_id == user.id)
        .order_by(ChatConversation.updated_at.desc())
        .limit(30)
    )
    return {"conversations": [
        {"id": c.id, "title": c.title, "created_at": c.created_at, "updated_at": c.updated_at}
        for c in result.scalars().all()
    ]}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(authorization, db)
    c_result = await db.execute(select(ChatConversation).where(
        ChatConversation.id == conversation_id, ChatConversation.user_id == user.id
    ))
    conversation = c_result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")
    m_result = await db.execute(select(ChatMessage).where(
        ChatMessage.conversation_id == conversation.id, ChatMessage.user_id == user.id
    ).order_by(ChatMessage.created_at.asc()).limit(200))
    return {"conversation": {"id": conversation.id, "title": conversation.title},
            "messages": [
                {"role": m.role, "content": m.content, "model_used": m.model_used,
                 "query_type": m.query_type, "token_cost": m.token_cost}
                for m in m_result.scalars().all()
            ]}


@router.post("")
async def chat(
    body: ChatRequest,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import StreamingResponse
    import json
    import time
    from litellm import acompletion

    user = await get_current_user(authorization, db)

    conversation = await _get_or_create_conversation(user, body, db)
    incoming_user_text = body.messages[-1].content if body.messages else ""
    await _save_message(db, conversation, user, "user", incoming_user_text)
    await db.commit()

    if user.tokens <= 0:
        raise HTTPException(
            status_code=402,
            detail="Token hakkın bitti. Mağazadan token al veya Pro / Elite plana geç.",
        )

    messages = [
        {"role": "system", "content": NEXORA_IDENTITY},
        *[m.model_dump() for m in body.messages],
    ]
    user_text = body.messages[-1].content if body.messages else ""
    query_type, models, estimated_cost, route_reason = llm_router.resolve(user_text, user.plan)

    if user.tokens < estimated_cost:
        raise HTTPException(
            status_code=402,
            detail=f"Bu işlem yaklaşık {estimated_cost} token. Kalan: {user.tokens}",
        )

    async def event_stream():
        started_at = time.perf_counter()
        full_content = ""
        selected_model = ""
        last_error = None

        for model in models:
            try:
                selected_model = model
                response = await acompletion(
                    model=model,
                    messages=messages,
                    temperature=body.temperature,
                    max_tokens=body.max_tokens,
                    stream=True,
                )

                yield f"event: meta\ndata: {json.dumps({'model_used': model, 'query_type': query_type, 'token_cost': estimated_cost, 'route_reason': route_reason})}\n\n"

                async for chunk in response:
                    try:
                        text = chunk.choices[0].delta.content or ""
                    except (AttributeError, IndexError, TypeError):
                        text = ""

                    if not text:
                        continue

                    full_content += text
                    for char in text:
                        yield f"data: {json.dumps({'content': char}, ensure_ascii=False)}\n\n"

                latency_ms = int((time.perf_counter() - started_at) * 1000)
                remaining = await deduct_tokens(user.email, estimated_cost, db)
                await _save_message(db, conversation, user, "assistant", full_content, selected_model, query_type, estimated_cost)
                await db.commit()
                yield f"event: done\ndata: {json.dumps({'content': '', 'tokens': remaining, 'remaining': remaining, 'token_cost': estimated_cost, 'latency_ms': latency_ms, 'model_used': selected_model, 'query_type': query_type, 'route_reason': route_reason, 'conversation_id': conversation.id})}\n\n"
                yield "event: end\ndata: {}\n\n"
                return
            except Exception as exc:
                last_error = exc
                continue

        detail = str(last_error)[:180] if last_error else "Model bulunamadı"
        yield f"event: error\ndata: {json.dumps({'detail': f'Zeka katmanı şu an yanıt veremiyor: {detail}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
