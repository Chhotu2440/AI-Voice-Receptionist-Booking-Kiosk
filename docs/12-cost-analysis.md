# 12 — Cost Analysis

**Actual vs estimate:** per-token/per-minute *rates* are actual published prices (doc 11 sources, 2026-11-10). Everything derived from them (session lengths, token counts, context re-billing) is an **estimate** until the bake-off measures billed usage. Model script: [`scripts/cost_model.py`](../scripts/cost_model.py). FX assumption: **₹88 = $1** (verify at time of budgeting).

## 1. Modelling assumptions

| Scenario | Customer speech | AI speech | Turns | Mic open (cascaded STT billing) |
|---|---|---|---|---|
| 30-second interaction | 0.15 min | 0.12 min | 3 | 0.4 min |
| 2-minute interaction (**typical booking**) | 0.7 min | 0.7 min | 12 | 1.8 min |
| 5-minute interaction | 1.8 min | 1.7 min | 30 | 4.5 min |

- System prompt + tool schemas ≈ 4,000 text tokens, re-sent each turn (cached where the provider supports it).
- Token rates: OpenAI user audio ≈ 600 tok/min, assistant audio ≈ 1,200 tok/min. Gemini 25 tok/s = 1,500 tok/min (both directions).
- Conversation audio context is re-billed each turn (OpenAI at cached audio rate; Gemini at the full input rate, as a conservative upper bound).

## 2. Per-session cost (USD, estimate)

| Provider / model | 30 s | 2 min | 5 min |
|---|---|---|---|
| OpenAI gpt-realtime-2.1-mini | $0.008 | **$0.033** | $0.086 |
| Gemini 3.8 Live (no caching assumed) | $0.016 | $0.098 | $0.385 |
| Cascaded (Sarvam STT/TTS + Gemini 3.5 Flash-Lite) | $0.011 | $0.062 | $0.220 |
| OpenAI gpt-realtime-2.1 (full) | $0.042 | $0.147 | $0.354 |

### Breakdown: 2-minute session

| Component | gpt-realtime-2.1-mini | gemini-3.8-live | Cascaded |
|---|---|---|---|
| Audio input (new) | $0.0042 | $0.0032 | $0.0102 (STT) |
| Audio output | $0.0168 | $0.0126 | $0.0159 (TTS) |
| Text (prompt, tools, tool outputs) | $0.0094 | $0.0441 | $0.0362 (LLM) |
| Re-billed audio context | $0.0023 | $0.0378 | — |
| **Total** | **$0.033 (≈ ₹2.9)** | **$0.098 (≈ ₹8.6)** | **$0.062 (≈ ₹5.5)** |

Cost-control levers built in: a short system prompt, tool schemas kept lean, truncating old audio turns once fields are captured (the state summary replaces history), the session cap at 10 min, and switching to touch-only when the spend cap is hit.

## 3. Monthly AI cost (assuming an average session of ~2 min; sessions include non-booking ones)

| Sessions / month | gpt-realtime-2.1-mini | gemini-3.8-live | Cascaded | gpt-realtime-2.1 |
|---|---|---|---|---|
| 500 | $16 (₹1.4k) | $49 (₹4.3k) | $31 (₹2.7k) | $74 (₹6.5k) |
| 1,000 | $33 (₹2.9k) | $98 (₹8.6k) | $62 (₹5.5k) | $147 (₹12.9k) |
| 3,000 | $98 (₹8.6k) | $293 (₹25.8k) | $187 (₹16.5k) | $441 (₹38.8k) |

## 4. Other operating costs (monthly, estimates)

| Item | Estimate | Notes |
|---|---|---|
| Hosting (VPS 4 vCPU/8 GB, Mumbai) + backups | ₹2,500–5,000 | doc 23 |
| Domain + TLS | ~₹100 | Let's Encrypt is free |
| WhatsApp utility template (India) | ~₹0.12–0.15 per delivered message. **From 1 Oct 2026, utility templates inside a 24 h window are also billable** (reseller reports; verify on Meta's rate card) | 1,000 confirmations ≈ ₹150 |
| SMS fallback (optional) | ~₹0.15–0.25/SMS + DLT registration | — |
| Razorpay (if enabled) | ~2% per transaction (standard plan; verify) | Payment workflow only |
| DaySchedule | $8/user/month until retired (if currently on a paid plan) | — |
| Monitoring (Uptime Kuma self-hosted / Better Stack free tier) | ₹0–1,500 | — |

## 5. Recommended monthly budget
- **AI:** budget **₹10,000/month** for the first 3 months. This covers ~1,000–3,000 sessions on the mini model with headroom for the bake-off and tuning. Alerts trigger at 50%, 80% and 100%, and the hard cap switches to touch-only mode.
- **Total run cost (excluding payment fees):** about **₹13,000–18,000/month** at launch, reviewed after month 1 using actual `ai_usage_logs`.

## 6. Usage tracking design
Every provider adapter reports `UsageRecord` at turn end (tokens by modality, from the provider's usage events). `ai_usage_logs.cost_usd` is computed from a versioned price table in `system_settings.ai.price_table` (editable when providers change prices). The admin dashboard shows cost today, this month, cost per session and cost per confirmed booking. The worker checks spend every 5 minutes against the daily and monthly caps.
