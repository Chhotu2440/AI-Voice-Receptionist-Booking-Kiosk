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

## 6. Voice streaming decision
Relay through our backend (ADR-005); provider keys never leave the server. If we switch to direct WebRTC (ADR-005b), the backend issues **short-lived ephemeral tokens** (OpenAI client secrets / Gemini ephemeral tokens), each scoped to one session with a ≤ 1 min start window.

## 7. Monitoring
Uptime checks (/readyz, kiosk heartbeat freshness), error tracking (Sentry self-hosted or SaaS free tier), metrics (Prometheus + Grafana or provider-native), alerts by email and WhatsApp to the owner/tech contact. See doc 24.
