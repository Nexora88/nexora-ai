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
from app.services.weather import weather_card
from app.api.market import fetch_twelvedata_quote, fetch_twelvedata_series, fetch_finnhub_intelligence
from app.core.config import get_settings
import re
import httpx

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

    # Agent tools: never let the LLM invent live weather/market values.
    live_context = []
    tool_meta = {}
    weather_match = re.search(
        r"(?:hava(?:\s+durumu)?|hava)\s*(?:nasıl|durumu)?\s*(?:için|icin|da|de)?\s*([A-Za-zÇĞİÖŞÜçğıöşü .-]{2,40})",
        user_text,
        re.IGNORECASE,
    )
    if weather_match and any(x in user_text.lower() for x in ("hava", "sıcak", "sicak", "yağmur", "yagmur", "rüzgar", "ruzgar", "hava durumu")):
        city = weather_match.group(1).strip(" .,-")
        city = re.split(r"\s+(?:nasıl|bugün|yarın|yarin|şimdi|simdi|kaç|kac|olacak|olur|durumu)\b", city, flags=re.I)[0].strip()
        city = re.sub(r"(?i)(?:['’]?(?:da|de|ta|te))$", "", city).strip()
        if city:
            try:
                w = await weather_card(city)
                if w.get("ok"):
                    live_context.append(
                        "CANLI HAVA ARACI SONUCU (Open-Meteo): " + str(w)
                    )
                    tool_meta["weather"] = w
                    route_reason += "|weather_tool"
            except Exception as exc:
                live_context.append(f"Hava aracı hata verdi: {str(exc)[:120]}")
    market_match = re.search(
        r"\b(?:([A-Z]{1,6})(?::[A-Z]{2,6})?|XU100|BIST ?100|THYAO|ASELS|AKBNK|GARAN|AAPL|TSLA|NVDA|MSFT|AMZN|META|GOOGL)\b",
        user_text.upper(),
    )
    if market_match and any(x in user_text.lower() for x in ("hisse", "borsa", "grafik", "fiyat", "kaç", "kac", "analiz", "bist", "stock", "share", "chart")):
        ticker = market_match.group(0).upper().replace(" ", "")
        if ticker == "BIST100":
            ticker = "XU100"
        try:
            q = await fetch_twelvedata_quote(ticker)
            series = await fetch_twelvedata_series(ticker, "1day", 60)
            fin = await fetch_finnhub_intelligence(ticker)
            if not q.get("error") and series.get("values"):
                tool_meta["market"] = {
                    "symbol": ticker,
                    "quote": q,
                    "series": series.get("values", []),
                    "news": fin.get("news", []),
                    "dividends": fin.get("dividends", []),
                    "sources": ["Twelve Data"] + (["Finnhub"] if fin.get("configured") else []),
                    "provider": "twelvedata",
                }
                live_context.append(
                    "CANLI PİYASA ARACI SONUCU (Twelve Data): " + str(tool_meta["market"])
                )
                route_reason += "|market_tool"
        except Exception as exc:
            live_context.append(f"Piyasa aracı hata verdi: {str(exc)[:120]}")

    # Web research: route explicit/current-news/source/link questions to Tavily when configured.
    settings = get_settings()
    search_terms = ("internette", "internette ara", "webde ara", "araştır", "arastir", "son haber", "haberleri", "kaynak", "link", "güncel", "guncel", "bugün", "bugun")
    if any(term in user_text.lower() for term in search_terms) and settings.TAVILY_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                sr = await client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": settings.TAVILY_API_KEY, "query": user_text, "search_depth": "advanced", "max_results": 6, "include_answer": True},
                )
                if sr.status_code < 300:
                    sd = sr.json()
                    results = sd.get("results", [])
                    web_pack = {
                        "answer": sd.get("answer"),
                        "results": [{"title": x.get("title"), "url": x.get("url"), "content": (x.get("content") or "")[:900]} for x in results],
                    }
                    tool_meta["web"] = web_pack
                    live_context.append("CANLI WEB ARAŞTIRMA (Tavily): " + str(web_pack))
                    route_reason += "|web_search"
        except Exception as exc:
            live_context.append(f"Web arama aracı hata verdi: {str(exc)[:120]}")

    if live_context:
        messages.append({
            "role": "system",
            "content": "\n\n".join(live_context) +
            "\nBu araç verilerini gerçek zamanlı veri olarak kullan; değerleri tahmin etme ve kaynağı belirt."
        })

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
                    model=model, messages=messages, temperature=body.temperature,
                    max_tokens=body.max_tokens, stream=False,
                )
                try:
                    full_content = (response.choices[0].message.content or '').strip()
                except (AttributeError, IndexError, TypeError):
                    full_content = ''
                if not full_content:
                    raise RuntimeError('Model returned an empty response; trying the next model.')
                yield f"event: meta\ndata: {json.dumps({'model_used': model, 'query_type': query_type, 'token_cost': estimated_cost, 'route_reason': route_reason, 'tools': tool_meta}, ensure_ascii=False)}\n\n"
                for char in full_content:
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
