import hmac
from dataclasses import dataclass
from hashlib import sha256
from typing import Optional, Protocol


@dataclass
class ProviderOrder:
    provider_order_id: str
    amount_paise: int
    currency: str
    public: dict  # safe-to-share config for the client SDK


@dataclass
class ProviderPayment:
    payment_id: str
    order_id: str
    status: str  # captured | failed | created
    amount_paise: int


@dataclass
class WebhookEvent:
    kind: str  # payment.captured | payment.failed
    provider_order_id: str
    provider_payment_id: str
    amount_paise: Optional[int]


def hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, sha256).hexdigest()


class PaymentProvider(Protocol):
    name: str

    def create_order(self, receipt: str, amount_paise: int, currency: str = "INR") -> ProviderOrder: ...
    def verify_signature(self, provider_order_id: str, provider_payment_id: str, signature: str) -> bool: ...
    def fetch_payment(self, provider_payment_id: str) -> Optional[ProviderPayment]: ...
    def verify_webhook(self, raw_body: bytes, signature: str) -> bool: ...
    def parse_webhook(self, payload: dict) -> Optional[WebhookEvent]: ...
