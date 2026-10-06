from collections import defaultdict, deque
from contextlib import asynccontextmanager
from time import monotonic

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import init_db
from app.api import (
    auth,
    chat,
    payments,
    webhooks,
    market,
    media,
    ship,
    permissions,
    plugins,
    weather,
)

settings = get_settings()
is_production = settings.ENVIRONMENT.lower() == "production"

# Lightweight process-local abuse control. Railway instances should additionally
# use an edge/WAF rate limit for distributed protection.
_rate_windows: dict[str, deque[float]] = defaultdict(deque)
_RATE_LIMIT = 60
_RATE_WINDOW_SECONDS = 60
_PROTECTED_PREFIXES = ("/api/v1/auth/", "/api/v1/chat", "/api/v1/media", "/api/v1/market")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Nexora AI — Hybrid intelligence · Ship · Weather · Plugins",
    version="0.3.1",
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    lifespan=lifespan,
)

allowed_origins = [settings.FRONTEND_URL.rstrip("/")]
if not is_production:
    allowed_origins.extend(["http://localhost:3000", "http://127.0.0.1:3000"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(allowed_origins)),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path

    if is_production and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if path.startswith(_PROTECTED_PREFIXES):
            now = monotonic()
            bucket = _rate_windows[client_ip]
            while bucket and now - bucket[0] > _RATE_WINDOW_SECONDS:
                bucket.popleft()
            if len(bucket) >= _RATE_LIMIT:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again later."},
                    headers={"Retry-After": "60"},
                )
            bucket.append(now)

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; connect-src 'self' https://nexora-ai-production-3a2e.up.railway.app https://ckxgbmvjehshgicafsjp.supabase.co; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
    if is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Cache-Control"] = "no-store" if path.startswith("/api/") else response.headers.get("Cache-Control", "")
    return response


app.include_router(auth.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(media.router, prefix="/api/v1")
app.include_router(payments.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(ship.router, prefix="/api/v1")
app.include_router(permissions.router, prefix="/api/v1")
app.include_router(plugins.router, prefix="/api/v1")
app.include_router(weather.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "slogan": "Veri • Zekâ • Gelecek",
        "version": "0.3.1",
        "status": "online",
        "security": "active",
        "modules": [
            "auth",
            "chat",
            "market",
            "media",
            "ship",
            "permissions",
            "plugins",
            "weather",
        ],
    }


@app.get("/health")
async def health():
    return {"status": "ok", "security": "active"}
