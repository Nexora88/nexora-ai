# Nexora AI — Railway backend

The repository is split operationally into:
- Vercel: Next.js frontend (frontend/)
- Railway: FastAPI backend (repository root Dockerfile)
- Railway/PostgreSQL: persistent production database

## Railway service
Connect `Nexora88/nexora-ai` to a Railway service and use the repository root as the service root.

Railway detects the root Dockerfile and starts:
uvicorn app.main:app --host 0.0.0.0 --port $PORT

Health check:
/health

## Required variables
Copy the values from the existing secure backend environment into the Railway service. Do not commit real secrets.

Required production variables:
- ENVIRONMENT=production
- DATABASE_URL=<Railway Postgres DATABASE_URL>
- SECRET_KEY=<existing secret>
- JWT_SECRET=<existing JWT secret>
- FRONTEND_URL=<Vercel frontend URL>
- GITHUB_REDIRECT_URI=https://<railway-domain>/api/v1/ship/callback

LLM/API/Stripe variables can be copied from the existing backend environment as needed.

## Vercel
Set:
NEXT_PUBLIC_API_URL=https://<railway-domain>/api/v1

The frontend remains deployed on Vercel. The API is no longer expected at a Vercel /api/v1 route.

Railway GitHub autodeploy should be enabled for main, so backend changes deploy after each push.
