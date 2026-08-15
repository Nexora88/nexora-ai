# Nexora AI

**Veri • Zekâ • Gelecek**

Multi-model hybrid AI assistant with automatic failover, free tier & advanced tools.

## Features
- Account system + 5 free messages
- Multi-provider LLM router with failover
- Pro ($12) & Elite ($29) plans ready
- Multilingual support
- Chat + Code + Homework + Stock analysis base

## Tech Stack
- FastAPI + LiteLLM
- JWT Auth
- Free models: Groq, Gemini, OpenRouter

## Quick Start
```bash
pip install -r requirements.txt
cp .env.example .env
# Add at least one free API key
uvicorn app.main:app --reload
