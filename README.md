# Nexora AI

**Veri · Zekâ · Gelecek**

> Not a chatbot. An intelligence system.

Nexora AI, sorunun türüne göre doğru modeli seçen, canlı veri araçlarına bağlanan ve isteğe bağlı olarak GitHub’a **PR üreten** hibrit bir zeka platformudur.

**Kurucu:** Ahmet Eymen Bakraç  

**Sürüm (backend):** `0.3.1`  

---

## Bu proje ne?

Tek bir LLM sarmalayıcısı değil. Ürün üç katmanda çalışır:

1. **Anlama** — niyet sınıflandırma (`fast` · `code` · `finance` · `deep` · `identity`)
2. **Yönlendirme** — çoklu sağlayıcı havuzu + failover (LiteLLM)
3. **Eylem** — market / hava / medya / GitHub Ship / code index / izinler

Son geliştirme hattı (özet):

| Commit / yön | İçerik |
|--------------|--------|
| Premium workspace | Sinematik thinking / intelligence UI |
| Agent tools | Canlı weather + market bağlantısı |
| Ship & plugins | GitHub PR, permissions, code index |
| Deploy | Frontend Vercel · Backend Railway · Postgres |

---

## Özellikler

### Zeka katmanı
- Hibrit **LLM router** (Groq, Gemini, OpenRouter, Mistral, Cohere, DeepSeek, …)
- Otomatik **failover** (model/sağlayıcı düşünce sıradaki)
- Token ekonomisi (işlem tipine göre maliyet)
- Kimlik: Nexora / kurucu bilgisi (system prompt)

### Ajan araçları
- **Market** — kripto / piyasa analizi (CoinGecko vb.)
- **Weather** — şehir bazlı kart + ajan mesajı (Open-Meteo; yedek key’ler opsiyonel)
- **Media** — dosya / görsel / ses analizi
- Sohbette araç seçimi ve stabil ajan yanıtları

### GitHub Ship (geliştirici eklentisi)
- OAuth ile hesap bağlama
- Varsayılan repo seçimi
- Branch + commit + **Pull Request** (doğrudan `main` zorunlu değil)
- **Multi-agent swarm:** PM → Coder → Security → (self-heal test) → PR raporu
- Secret Guard (key sızıntısı tarama)
- Diff preview / repo memory / dinamik **code index**

### Güvenlik & hesap
- JWT auth · rate limit (production)
- Güvenlik header’ları (CSP, HSTS, nosniff, …)
- Plugin izinleri: `always` · `ask` · `deny`
- Stripe iskeleti (Pro / Elite)
- Opsiyonel Supabase alanları (`.env.example`)

### Arayüz
- Next.js premium intelligence workspace
- Cinematic thinking katmanı
- `/extensions` — GitHub Kur, izinler, repo index

---

## Mimari

```text
┌──────────────────────┐         ┌─────────────────────────────┐
│  Next.js (frontend/) │  HTTPS  │  FastAPI (app/)              │
│  Vercel              │ ──────► │  Railway (Dockerfile)        │
└──────────────────────┘         └──────────────┬──────────────┘
                                                │
                                     ┌──────────▼──────────┐
                                     │  PostgreSQL (prod)  │
                                     │  SQLite (local)     │
                                     └──────────┬──────────┘
                                                │
                          ┌─────────────────────┼─────────────────────┐
                          │                     │                     │
                    LiteLLM Router        Weather/Market         GitHub API
                    (multi-model)         (live tools)           (Ship / PR)
