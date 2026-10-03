"""Vercel Python entrypoint for Nexora AI.

The full FastAPI application is imported lazily so a missing production secret
cannot take down the entire deployment. Health/status remain available and the
frontend receives a clear 503 for backend features until deployment secrets are
configured in the platform (never committed to Git).
"""
from fastapi import FastAPI, HTTPException

try:
    from app.main import app as app
    IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - deployment safety net
    IMPORT_ERROR = type(exc).__name__
    app = FastAPI(title="Nexora AI")

    @app.get("/")
    async def fallback_root():
        return {
            "name": "Nexora AI",
            "status": "shell-online",
            "backend": "configuration-required",
        }

    @app.get("/health")
    async def fallback_health():
        return {
            "status": "ok",
            "backend": "configuration-required",
            "error_type": IMPORT_ERROR,
        }

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def fallback_api(path: str):
        raise HTTPException(
            status_code=503,
            detail="Nexora backend is not configured in this deployment. Add runtime secrets in Vercel; never commit .env files.",
        )
