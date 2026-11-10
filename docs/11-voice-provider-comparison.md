# 11 — Voice Provider Comparison

Researched 2026-11-10. **Prices** are from the official pricing pages (sources below). **Capability** rows marked (doc) come from provider documentation. Rows marked (est.) are our expectations and **must be measured** in the bake-off. No provider is selected on marketing claims.

## 1. Candidates

| | OpenAI Realtime `gpt-realtime-2.1-mini` | OpenAI Realtime `gpt-realtime-2.1` | Google `gemini-3.8-live` | Cascaded: Sarvam STT + LLM + TTS |
|---|---|---|---|---|
| Architecture | Speech-to-speech | Speech-to-speech | Speech-to-speech (native audio) | STT → text LLM (e.g. `gemini-3.5-flash-lite`) → TTS (Sarvam Bulbul) |
| Audio input price | $10 / 1M tok (cached $0.30) | $32 / 1M (cached $0.40) | $3 / 1M (~$0.005/min) | STT ₹30/hour |
| Audio output price | $20 / 1M | $64 / 1M | $12 / 1M (~$0.018/min) | Bulbul v3 ₹30/10k chars; v4 Flash ~₹20/10k (verify) |
| Text in / out | $0.60 / $2.40 | $4 / $24 | $0.75 / $4.50 | Flash-lite $0.30 / $2.50 |
| Hindi / Hinglish (est.) | Good, needs measurement | Best of OpenAI | Strong multilingual (Google ASR heritage), needs measurement | **Best Indic ASR** (Indian-trained), natural Indian TTS voices |
| Indian accent robustness (est.) | Good | Good | Good | Very good |
| Latency (est.) | ~0.6–1.0 s TTFA | ~0.7–1.1 s | ~0.6–1.0 s | ~1.2–2.0 s (3 hops) |
| Barge-in | Server VAD + `response.cancel` + truncate (doc) | same | Automatic VAD interruption (doc) | Must be built (our VAD + cancel TTS) |
| Function calling | Mature, reliable (doc) | Most reliable | Supported (doc), reliability to measure | Via text LLM (mature) |
| Transport | WebSocket, WebRTC, SIP (doc) | same | WebSocket (doc) | REST/WebSocket streaming |
| Ephemeral tokens | Yes (client secrets) (doc) | Yes | Yes (doc) | N/A (server-side) |
| Session limits | Long sessions supported; verify current max | same | Audio sessions are time-limited without context compression; verify | None |
| Context billing | Prior turns re-billed as input; cached audio cheap | same | Prior context re-billed per turn | Text only (cheap) |
| Privacy (paid tier) | API data not used for training by default (verify DPA) | same | Paid tier "not used to improve products" (pricing page) | Indian provider; check DPA/data residency |
| Lock-in | Low (behind our adapter) | Low | Low | Low (3 swappable parts) |

## 2. Assessment
- **gpt-realtime-2.1-mini** is our primary candidate. It has the lowest modelled cost per 2-minute booking (~$0.033), a proven function-calling and interruption protocol, and cheap cached context.
- **gemini-3.8-live** is the challenger. It has the cheapest raw audio rates, but in our model the per-turn re-billing of uncached context makes it ~3× costlier per session. If Google's implicit caching applies to Live sessions, the gap closes. **Measure actual billed tokens in the bake-off.**
- **gpt-realtime-2.1 (full)** is reserved as a quality escalation if mini fails Hindi or tool reliability. It costs ~4.5× more.
- **Cascaded (Sarvam)** is the fallback if both speech-to-speech models fail Hinglish/phone-number accuracy. It wins on Indic ASR, but it has the highest latency and the most engineering (we own VAD/barge-in).

## 3. Other providers noted (not shortlisted for v1)
ElevenLabs Conversational AI, Deepgram Voice Agent, Azure OpenAI Realtime (same OpenAI models under an Azure contract; useful if enterprise billing is preferred), and Vapi/Retell (orchestration platforms that add a margin and are designed for telephony). These were not shortlisted because they add a layer without solving our main risk, Hinglish accuracy, better than the direct options.

## 4. Bake-off plan (task VOICE-01, ~4 days)
- Same kiosk hardware, mic and speaker. The same 240 recorded conversations (see doc 10 §7) are replayed, plus 20 live sessions by staff.
- Metrics and weights: Hinglish/Hindi task success 30%, phone number exact-match 15%, TTFA p50/p95 15%, tool-call validity 15%, barge-in stop time 5%, voice naturalness (staff MOS 1–5) 10%, **actual billed cost per completed booking** 10%.
- Decision rule: the highest weighted score wins. Any candidate with an invented-fact rate above 0 after prompt tuning, or phone exact-match below 95% (after read-back), is disqualified.

## Sources
- Google Gemini API pricing: https://aistudio.google.com/docs/pricing (redirect from ai.google.dev/gemini-api/docs/pricing), fetched 2026-11-10
- OpenAI API pricing: https://developers.openai.com/api/docs/pricing, fetched 2026-11-10
- Sarvam AI pricing: https://docs.sarvam.ai/api/pricing and https://sarvam.ai/api-pricing. Bulbul v4 Flash pricing is inconsistent across Sarvam pages; a promo price ends 12 Nov 2026 (https://runtimewire.com/article/sarvam-bulbul-v4-flash-pricing-launch). **Verify before quoting.**
- Third-party summaries used only to cross-check: cekura.ai, tokenkarma.app (Gemini Live); aireiter.com, forasoft.com (OpenAI Realtime)
