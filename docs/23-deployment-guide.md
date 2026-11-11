# 23 — Infrastructure & Deployment Plan

> Status: **plan**. Step-by-step commands will be filled in and verified during REL-03. Indicative hosting prices are estimates to confirm at purchase.

## 1. Hosting comparison (1 kiosk + web booking + admin)

| Option | Spec | Est. monthly | Pros | Cons |
|---|---|---|---|---|
| **AWS Lightsail (Mumbai)** | 4 vCPU / 8 GB / 160 GB | ~$40–50 | Mumbai region (low latency to Delhi), snapshots, simple pricing, AWS path later | Slightly pricier than budget VPS |
| AWS EC2 t3/t4g.large + EBS (Mumbai) | 2 vCPU / 8 GB | ~$60–75 + EBS | Full AWS ecosystem | More ops; cost |
| DigitalOcean / Vultr / Linode (Bangalore/Mumbai) | 4 vCPU / 8 GB | ~$40–50 | Simple, India regions | — |
| Hetzner | 4 vCPU / 8 GB | ~$10–15 | Cheapest | No India region → +120–150 ms RTT; hurts voice latency |
| Managed DB (RDS MySQL) add-on | db.t4g.micro/small | +$15–30 | Managed backups/PITR | Extra cost; optional |

**Recommendation:** AWS Lightsail or DigitalOcean in Mumbai/Bangalore, 4 vCPU/8 GB, with MySQL in Docker on the same host. Backups use automated daily snapshots plus `mysqldump`/binlog shipping to S3-compatible storage. Move MySQL to managed RDS when there are more than 3 kiosks or the business wants PITR without ops work.

## 2. Runtime topology (Docker Compose, one host)
`nginx` (TLS via Certbot, static kiosk/admin/web builds, reverse proxy, WS upgrade, rate limits) → `api` (gunicorn -k uvicorn.workers.UvicornWorker, 3 workers) · `voice` (uvicorn, 1–2 workers; sticky WS) · `worker` (ARQ) · `mysql:8.4` (volume, binlog on) · `redis:7` (AOF on) · `uptime-kuma` (optional). Log rotation via Docker `json-file` `max-size`. All containers have healthchecks and `restart: unless-stopped`. Graceful shutdown: SIGTERM → stop accepting → drain WS (tell the kiosk to reconnect) → 30 s timeout.

## 3. Environments
`dev` (local compose, mock providers allowed and explicitly flagged by `APP_ENV=dev`) · `staging` (same compose on a small VPS, real provider sandbox/test keys, Razorpay test mode, WhatsApp test number) · `prod`. Mock adapters **refuse to start** when `APP_ENV=prod`.

## 4. CI/CD (GitHub Actions)
PR: lint → type-check → unit → integration (MySQL+Redis services) → frontend tests → Playwright (against compose) → scans. Main: build and push images (GHCR) tagged by SHA → deploy to staging (SSH + `docker compose pull && up -d` + `alembic upgrade head` as a one-off job) → manual approval → prod. Migrations must be backward-compatible (expand/contract) so rollback = previous image.

## 5. Kiosk deployment
- OS: Windows 11 Pro Assigned Access with Chrome kiosk, **or** Ubuntu 24.04 + `chromium --kiosk --autoplay-policy=no-user-gesture-required --use-fake-ui-for-media-stream` (only for our origin, pre-granted camera/mic permissions via policy).
- Chrome enterprise policies: `VideoCaptureAllowedUrls`, `AudioCaptureAllowedUrls`, disable devtools, disable translate prompts, homepage = kiosk URL.
- Auto-start on boot, auto-login kiosk user, nightly reboot at 04:00, OS updates scheduled outside business hours.
- The kiosk app is served from the server (always the latest version). A service worker allows an offline shell.
- **Self-healing layers (KIOSK-06):**
  1. **Browser restart:** `scripts/kiosk/kiosk-browser.service` (Ubuntu, systemd `Restart=always`) or `scripts/kiosk/start-kiosk.ps1` (Windows, Task Scheduler at logon) reopens the browser within seconds if it crashes or is closed.
  2. **Frozen page:** the service worker reloads the page if it stops sending "alive" signals for 12 s.
  3. **Crashed screen:** a render error shows "Restarting…" (EN/HI) and reloads after 5 s.
  4. **Network:** a reload with no network still shows the kiosk with the "Reconnecting" banner (cached shell); a socket with no reply for 40 s is treated as dead and reconnected; after 5 min offline the page reloads once the shell is cached.
  5. **Updates and memory:** a new build is picked up the next time the kiosk is idle for 10 s; the page also refreshes once a day while idle.
  Every reload starts at IDLE with an empty store, so no customer data survives.
- **Nginx headers for the kiosk build** (required, or kiosks may keep an old version):
  `location = /sw.js { add_header Cache-Control "no-cache"; }`, `location = /index.html { add_header Cache-Control "no-cache"; }`,
  `location /assets/ { add_header Cache-Control "public, max-age=31536000, immutable"; }`. The service worker needs HTTPS (localhost is exempt for development).
- The service worker is only registered in production builds (`npm run build`); `npm run dev` runs without it.

## 6. Voice streaming decision
Relay through our backend (ADR-005); provider keys never leave the server. If we switch to direct WebRTC (ADR-005b), the backend issues **short-lived ephemeral tokens** (OpenAI client secrets / Gemini ephemeral tokens), each scoped to one session with a ≤ 1 min start window.

## 7. Monitoring
Uptime checks (/readyz, kiosk heartbeat freshness), error tracking (Sentry self-hosted or SaaS free tier), metrics (Prometheus + Grafana or provider-native), alerts by email and WhatsApp to the owner/tech contact. See doc 24.

## 8. WhatsApp setup (Interakt)
Booking confirmations are sent as an approved WhatsApp **utility** template through Interakt.

1. In Interakt, create a template whose code name matches `INTERAKT_BOOKING_TEMPLATE` (default `booking_confirmation`), category **Utility**, language **English**, and get Meta approval. The body must have **8 variables in this order**:
   ```
   Hi {{1}}, your Play Laser Tag booking is confirmed! 🎯
   Booking ref: {{2}}
   Date: {{3}}
   Time: {{4}}
   Package: {{5}} for {{6}} players
   Total: {{7}} ({{8}})
   See you at T-49, Hauz Khas Village. Show this message at the reception desk.
   ```
   The variables are filled from the booking: name, reference, date, time, package, players, total and payment status, for example "Pay at reception".
2. Put the API key in `INTERAKT_API_KEY` in `backend/.env`, along with a random `INTERAKT_WEBHOOK_SECRET`.
3. In Interakt's Developer Settings, set the webhook URL to `https://<domain>/api/v1/webhooks/interakt/<INTERAKT_WEBHOOK_SECRET>`. Enable the message status events (`message_api_sent/delivered/read/failed`). Interakt webhooks need the Growth or Advanced plan. Without them, messages still send, but stay at "SENT" in the log.
4. Check the log at `GET /api/v1/admin/notifications`. Status moves QUEUED → SENT → DELIVERED → READ. FAILED and SKIPPED rows carry the reason. Retryable errors are retried 3 times (30 s, 2 min, 10 min). The worker process must be running for retries.
