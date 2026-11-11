"""Interakt WhatsApp Business API client (send approved templates).

API (Interakt resource center, checked 2026-11-11):
  POST https://api.interakt.ai/v1/public/message/
  Authorization: Basic <API key from Interakt > Settings > Developer Settings>
  {"countryCode": "+91", "phoneNumber": "9876543210", "callbackData": "<ours>", "type": "Template",
   "template": {"name": "<template code name>", "languageCode": "en", "bodyValues": ["...", ...]}}
  -> {"result": true, "message": "Message created successfully", "id": "<message id>"}
Delivery status is NOT in the response; it arrives later via webhooks
(message_api_sent / delivered / read / failed).
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

URL = "https://api.interakt.ai/v1/public/message/"


@dataclass(frozen=True)
class SendResult:
    ok: bool
    message_id: str | None = None
    error: str | None = None
    retryable: bool = False


class InteraktClient:
    def __init__(
        self, api_key: str, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 15
    ) -> None:
        self._headers = {"Authorization": f"Basic {api_key}", "Content-Type": "application/json"}
        self._transport = transport
        self._timeout = timeout

    async def send_template(
        self,
        *,
        phone_e164: str,
        template: str,
        language: str,
        body_values: list[str],
        callback_data: str,
    ) -> SendResult:
        if not phone_e164.startswith("+91") or len(phone_e164) != 13:
            return SendResult(ok=False, error="unsupported phone number")
        payload = {
            "countryCode": "+91",
            "phoneNumber": phone_e164[3:],
            "callbackData": callback_data[:512],
            "type": "Template",
            "template": {"name": template, "languageCode": language, "bodyValues": body_values},
        }
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as client:
                r = await client.post(URL, json=payload, headers=self._headers)
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"network: {type(exc).__name__}", retryable=True)
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code >= 500 or r.status_code == 429:
            return SendResult(ok=False, error=f"HTTP {r.status_code}", retryable=True)
        if r.status_code >= 400 or not data.get("result"):
            return SendResult(ok=False, error=str(data.get("message") or f"HTTP {r.status_code}")[:300])
        return SendResult(ok=True, message_id=str(data.get("id")) if data.get("id") else None)
