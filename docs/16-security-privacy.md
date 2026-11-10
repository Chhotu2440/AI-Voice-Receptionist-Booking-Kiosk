# 16 — Security & Privacy Plan

## 1. Threat model (summary)

| Threat | Control |
|---|---|
| Stolen provider API keys | Keys only in server env/secret store. Never in kiosk or browser bundles. Rotated quarterly and on staff change |
| Kiosk device compromise (someone at the kiosk) | Chrome kiosk mode, OS lockdown, device JWT scoped to kiosk endpoints only; a device can't list customers or bookings beyond its own session |
| Kiosk impersonation | Device secret + JWT; disable in admin instantly; IP allowlist optional |
| Admin account takeover | Argon2id, lockout + rate limits, TOTP for OWNER/MANAGER, refresh-token reuse detection, audit log |
| Oversell / booking abuse via public web page | Holds per IP limit, CAPTCHA on booking POST, idempotency, capacity constraint |
| Voice prompt injection | No privileged tools; server-side validation; discount/price rules not in model control |
| Webhook spoofing | HMAC signature verification (Meta `X-Hub-Signature-256`, Razorpay), dedupe table |
| SQL injection | SQLAlchemy parameterized queries only; no raw SQL from inputs; AI has no query tool |
| XSS | React escaping; strict CSP (`default-src 'self'`; `connect-src` to own API only); no `dangerouslySetInnerHTML` |
| Data leak via errors | Error sanitizer; stack traces only in logs; request_id returned |
| Session leakage between customers | Kiosk store in memory only; `session.reset` on complete/timeout; server binds data to kiosk_session_id; new session = new id |

## 2. Controls checklist
HTTPS everywhere (TLS 1.2+, HSTS) · WSS with JWT on connect + Origin check · RBAC with least privilege · secrets via `.env` on server (chmod 600), plan to move to a secret manager when multi-server · input validation on every schema · rate limiting (Nginx + Redis) · secure cookies (HttpOnly, Secure, SameSite=Strict) · audit logs append-only · nightly encrypted backups + monthly restore test · dependency scanning (`pip-audit`, `npm audit`, GitHub Dependabot) and container scanning (Trivy) in CI · SAST (Bandit, Semgrep) · DB users: app user without DDL; migration user separate.

## 3. Privacy
- **Camera:** face *detection* only, on-device, frames discarded immediately. No recognition, no embeddings, no emotion/age/gender inference. Notice on the idle screen and a physical sign at the kiosk.
- **Audio:** streamed to the AI provider for live processing only. **Not recorded by us by default.** Transcript retention (for quality improvement) is **off** by default. If enabled, it needs explicit opt-in at the summary screen, 30-day retention, and PII redaction of the phone number.
- **Data minimization:** name and mobile are required. Email is optional. Birthday age is optional. Birthday-person name is optional.
- **Children:** the kiosk does not knowingly collect children's data beyond an optional birthday person's first name/age entered by the adult booker. The adult (booker) is the data principal. We do not profile or track minors.
- **Masking:** phone displayed as `98•••••210` on public screens and in logs (`to_masked`).
- **Retention (configurable, defaults):** bookings + customer data 24 months after last visit, then anonymized. Kiosk sessions/AI usage (no PII) 24 months. Notification logs 12 months. Webhook payloads 90 days. Audit logs 3 years.
- **Data principal rights:** admin workflow for access, correction, and erasure (anonymize customer, retain booking financial record with a pseudonymized customer).

## 4. DPDP Act 2023 & DPDP Rules: applicability notes
- The **Digital Personal Data Protection Act, 2023** applies to the digital personal data we collect (name, phone, booking details). The **DPDP Rules, 2025** were notified in **November 2025** with a phased commencement. Most Data Fiduciary obligations (notice, consent, security safeguards, breach notification, retention/erasure) take effect **after an ~18-month transition (around May 2027)**. **Verify the exact commencement dates with counsel at implementation time.** We build to the full standard now, so there's no retrofit.
- Design implications we implement:
  1. **Notice** in clear language (EN + HI) before collecting data: purpose (booking + confirmation), what's collected, retention, how to withdraw/erase, grievance contact.
  2. **Consent:** booking-processing relies on the customer's request for the service (and consent captured at Confirm). WhatsApp messaging and transcript retention use **separate, unbundled, opt-in** consents recorded in `customer_consents` with the notice version.
  3. **Children:** verifiable parental consent applies if we processed a child's data as the principal. Our design avoids making a child the data principal (the adult books). The birthday child's optional details are captured under the adult's consent. **Legal review recommended.**
  4. **Security safeguards & breach response:** encryption in transit, access control, logging, a breach runbook (doc 24) including notification to the Data Protection Board and affected principals as the Rules prescribe.
  5. **Processors:** AI provider, Meta (WhatsApp), Razorpay, hosting. Maintain a processor register and DPAs. Review cross-border transfer status (audio is processed outside India by OpenAI/Google).
- **Not legal advice.** Business decision D-09 asks the owner to have the privacy notice reviewed by counsel before go-live.
