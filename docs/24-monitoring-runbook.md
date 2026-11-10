# 24 — Monitoring Runbook

> Draft. Finalized in REL-03 once dashboards and alert channels exist.

## Signals & alerts

| Signal | Threshold | Severity | First response |
|---|---|---|---|
| `/readyz` failing | 2 consecutive (1 min) | P1 | Check `docker compose ps`; logs of failing dependency |
| Kiosk heartbeat stale | > 3 min in business hours | P1 | Call venue; check power/network; remote reboot |
| AI provider error rate | > 10% of sessions in 15 min | P2 | Switch provider in admin (if second adapter live) or force touch-only |
| AI spend | 50/80/100% of daily or monthly cap | P3/P2/P1 | Review usage; at 100% kiosk auto-switches to touch-only |
| Booking creation errors | > 2 in 10 min | P1 | Check DB locks/deadlocks; logs by request_id |
| Hold expiry job lag | oldest ACTIVE hold > TTL + 2 min | P2 | Restart worker; verify Redis |
| WhatsApp failures | > 20% in 1 h | P3 | Check template status, token expiry, Meta status |
| Disk usage | > 80% | P2 | Rotate logs, prune images, expand volume |
| Backup job | missing for 26 h | P1 | Run manually; investigate |

## Common procedures
- **Force touch-only:** Admin → Kiosks → [device] → Voice: Off (takes effect at the next session).
- **Restart services:** `docker compose restart api voice worker` (kiosk reconnects automatically).
- **Release stuck holds:** Admin → Bookings → Holds → Release (audited), or `python -m app.cli release-expired-holds`.
- **Rotate a provider key:** update the server `.env` → `docker compose up -d voice` → revoke the old key at the provider.
- **Data breach suspicion:** isolate (rotate secrets, disable affected accounts), preserve logs, assess scope, notify owner and counsel. Follow DPDP breach notification obligations (doc 16 §4).
