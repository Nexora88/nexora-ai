# Nexora AI

**Veri · Zekâ · Gelecek**

> Not a chatbot. An intelligence system.

Nexora, sorunun türüne göre doğru motoru seçen **hibrit çoklu-model** zeka sistemidir.  
Tek bir API sarmalayıcısı değil: **niyet → model havuzu → failover → token ekonomisi**.

Kurucu: **Ahmet Eymen Bakraç**

---

## Ürün özeti

| Katman | Ne yapar |
|--------|----------|
| **Router** | Soru tipi: `fast` · `code` · `finance` · `deep` · `identity` |
| **Failover** | Bir sağlayıcı düşünce sıradaki modele geçer |
| **Token** | Kayıtta 50 token; işlem tipine göre 1–3 (medya ek ücret) |
| **Chat** | Kimlikli sistem prompt, çok dilli sohbet |
| **Market** | Kripto veri (CoinGecko) + temkinli analiz |
| **Media** | Dosya / görsel / ses yükleme (video yakında) |

**Token maliyeti (metin):** hızlı/kimlik `1` · kod/derin `2` · finans `3`  
**Medya ek:** görsel/belge `+2` · ses `+3` · video `+4` (planlı)

---

## Mimari

```text
┌─────────────────┐         ┌──────────────────────────┐
│  Next.js        │  HTTP   │  FastAPI                 │
│  (frontend/)    │ ──────► │  /api/v1/*               │
│  Vercel         │         │  Railway / VPS önerilir  │
└─────────────────┘         └────────────┬─────────────┘
                                         │
                              ┌──────────▼──────────┐
                              │  SQLite (lokal)     │
                              │  PostgreSQL (prod)  │
                              └─────────────────────┘
                                         │
                              ┌──────────▼──────────┐
                              │  LiteLLM Router     │
                              │  Groq · Gemini · …  │
                              └─────────────────────┘
