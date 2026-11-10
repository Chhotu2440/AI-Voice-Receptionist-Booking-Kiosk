# 25 — Disaster Recovery

> Draft. Restore drill is task REL-03.

| Item | Target |
|---|---|
| RPO | ≤ 15 minutes (binlog shipping every 5–15 min) |
| RTO | ≤ 2 hours to a fresh VPS |

## Backups
- **MySQL:** nightly `mysqldump --single-transaction` (or XtraBackup) + binlogs shipped every ≤ 15 min, encrypted (age/GPG), uploaded to off-site object storage. Retained 7 daily, 4 weekly, 6 monthly.
- **Server snapshot:** daily (provider), retained 7 days.
- **Config:** `.env` kept in an encrypted password-manager entry owned by the business; infrastructure files in git.
- Redis is not backed up as a source of truth. Holds are rebuilt from MySQL on start (`ACTIVE` holds re-scheduled).

## Recovery scenarios
1. **App container failure:** auto-restart → if crash-looping, roll back to the previous image tag.
2. **Host loss:** provision a new VPS → install Docker → restore `.env` → `docker compose up` → restore the latest dump + replay binlogs → point DNS (TTL 300 s) → verify with the reconciliation report (bookings count per day).
3. **Bad migration / data corruption:** stop writes (maintenance flag → kiosk shows "Please see reception") → point-in-time restore to a new DB → verify → switch.
4. **Kiosk hardware failure:** spare-parts plan (keep a spare webcam + speakerphone). Staff take bookings in the admin dashboard meanwhile.
5. **Prolonged internet outage at venue:** staff use the admin dashboard on a phone hotspot. The kiosk shows an offline screen.

## Manual fallback
A printable "today's bookings" sheet is exported by staff every morning (admin → Bookings → Print day), so walk-ins can still be checked during a total outage.
