import hmac
from typing import Optional

import httpx

from app.payments.base import ProviderOrder, ProviderPayment, WebhookEvent, hmac_hex

API = "https://api.razorpay.com/v1"


class RazorpayPayments:
    """Razorpay server-side integration (orders API, signature + webhook verification).
    Requires real keys; run in Razorpay TEST mode until you complete their go-live checks."""
    name = "razorpay"

    def __init__(self, key_id: str, key_secret: str, webhook_secret: str):
        self.key_id, self.key_secret, self.webhook_secret = key_id, key_secret, webhook_secret

    def create_order(self, receipt: str, amount_paise: int, currency: str = "INR") -> ProviderOrder:
        r = httpx.post(f"{API}/orders", auth=(self.key_id, self.key_secret), timeout=20,
                       json={"amount": amount_paise, "currency": currency, "receipt": receipt[:40]})
        r.raise_for_status()
        d = r.json()
        return ProviderOrder(d["id"], d["amount"], d["currency"], {"provider": "razorpay", "key_id": self.key_id})

    def verify_signature(self, provider_order_id: str, provider_payment_id: str, signature: str) -> bool:
        expected = hmac_hex(self.key_secret, f"{provider_order_id}|{provider_payment_id}".encode())
        return hmac.compare_digest(expected, signature or "")

    def fetch_payment(self, provider_payment_id: str) -> Optional[ProviderPayment]:
        r = httpx.get(f"{API}/payments/{provider_payment_id}", auth=(self.key_id, self.key_secret), timeout=20)
        if r.status_code != 200:
            return None
        d = r.json()
        status = "captured" if d.get("status") == "captured" else "failed" if d.get("status") == "failed" else "created"
        return ProviderPayment(d["id"], d.get("order_id", ""), status, int(d.get("amount", 0)))

    def verify_webhook(self, raw_body: bytes, signature: str) -> bool:
        return hmac.compare_digest(hmac_hex(self.webhook_secret, raw_body), signature or "")

    def parse_webhook(self, payload: dict) -> Optional[WebhookEvent]:
        kind = payload.get("event")
        if kind not in ("payment.captured", "payment.failed"):
            return None
        e = payload.get("payload", {}).get("payment", {}).get("entity", {})
        return WebhookEvent(kind, e.get("order_id", ""), e.get("id", ""), e.get("amount"))
