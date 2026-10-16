import hmac
import secrets
from typing import Optional

from app.payments.base import ProviderOrder, ProviderPayment, WebhookEvent, hmac_hex


class MockPayments:
    """DEVELOPMENT ONLY. Signs like a real gateway so the server-side verification path is identical."""
    name = "mock"

    def __init__(self, secret: str):
        self.secret = secret
        self.orders: dict[str, int] = {}
        self.payments: dict[str, ProviderPayment] = {}

    def create_order(self, receipt: str, amount_paise: int, currency: str = "INR") -> ProviderOrder:
        oid = "order_mock_" + secrets.token_hex(6)
        self.orders[oid] = amount_paise
        return ProviderOrder(oid, amount_paise, currency, {"provider": "mock"})

    def simulate(self, provider_order_id: str, success: bool) -> tuple[str, str]:
        """Stand-in for the customer paying on the gateway. Returns (payment_id, signature)."""
        pid = "pay_mock_" + secrets.token_hex(6)
        self.payments[pid] = ProviderPayment(pid, provider_order_id, "captured" if success else "failed",
                                             self.orders[provider_order_id])
        return pid, self.sign(provider_order_id, pid)

    def sign(self, provider_order_id: str, provider_payment_id: str) -> str:
        return hmac_hex(self.secret, f"{provider_order_id}|{provider_payment_id}".encode())

    def verify_signature(self, provider_order_id: str, provider_payment_id: str, signature: str) -> bool:
        return hmac.compare_digest(self.sign(provider_order_id, provider_payment_id), signature or "")

    def fetch_payment(self, provider_payment_id: str) -> Optional[ProviderPayment]:
        return self.payments.get(provider_payment_id)

    def verify_webhook(self, raw_body: bytes, signature: str) -> bool:
        return hmac.compare_digest(hmac_hex(self.secret, raw_body), signature or "")

    def parse_webhook(self, payload: dict) -> Optional[WebhookEvent]:
        kind = payload.get("event")
        if kind not in ("payment.captured", "payment.failed"):
            return None
        p = payload.get("payload", {})
        return WebhookEvent(kind, p.get("order_id", ""), p.get("payment_id", ""), p.get("amount"))
