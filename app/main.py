from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Nexora AI — Hybrid intelligence · Ship · Plugins · Data · Intelligence · Future",
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://nexora.ai",
        "https://www.nexora.ai",
        "https://nexoraai.com",
        "https://www.nexoraai.com",
        "https://nexora-ai-dun.vercel.app",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core
app.include_router(auth.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(media.router, prefix="/api/v1")

# Payments
app.include_router(payments.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")

# Devrim katmanı
app.include_router(ship.router, prefix="/api/v1")
app.include_router(permissions.router, prefix="/api/v1")
app.include_router(plugins.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "slogan": "Veri • Zekâ • Gelecek",
        "version": "0.3.0",
        "status": "online",
        "docs": "/docs",
        "modules": [
            "chat",
            "market",
            "media",
            "ship",
            "permissions",
            "plugins",
        ],
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
