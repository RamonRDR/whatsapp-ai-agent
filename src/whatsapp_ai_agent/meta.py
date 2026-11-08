"""Official Meta Graph API adapter. No real sends unless explicitly enabled."""

import asyncio
from datetime import datetime, timedelta

import httpx

from whatsapp_ai_agent.config import Settings


class OutboundBlocked(Exception):
    pass


class MetaDeliveryError(Exception):
    pass


def within_customer_window(last_inbound: datetime | None, now: datetime) -> bool:
    return bool(last_inbound and now - last_inbound < timedelta(hours=24)
                and last_inbound <= now)


class MetaClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    async def send_text(
        self, recipient: str, body: str, last_inbound: datetime | None
    ) -> dict:
        if not self.settings.enable_real_send:
            raise OutboundBlocked("Real message delivery is disabled")
        if not within_customer_window(last_inbound, datetime.utcnow()):
            raise OutboundBlocked("Outside customer-service window; template required")
        if not recipient.isdigit() or not 7 <= len(recipient) <= 15:
            raise ValueError("Invalid recipient")
        if not body or len(body) > 4096:
            raise ValueError("Invalid message size")
        url = ("https://graph.facebook.com/" + self.settings.meta_graph_version + "/"
               + self.settings.meta_phone_number_id + "/messages")
        payload = {"messaging_product": "whatsapp", "to": recipient,
                   "type": "text", "text": {"preview_url": False, "body": body}}
        headers = {"Authorization": "Bearer " + self.settings.meta_access_token}
        async with httpx.AsyncClient(timeout=8, transport=self.transport) as client:
            for attempt in range(3):
                try:
                    response = await client.post(url, json=payload, headers=headers)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    if attempt == 2:
                        raise MetaDeliveryError("Meta transport failure") from exc
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        await asyncio.sleep(0.25 * (attempt + 1))
                        continue
                if response.is_error:
                    raise MetaDeliveryError("Meta API returned HTTP " + str(response.status_code))
                return response.json()
        raise MetaDeliveryError("Meta API retries exhausted")
