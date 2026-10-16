from app.core.config import Settings
from app.payments.base import PaymentProvider
from app.payments.mock import MockPayments
from app.payments.razorpay import RazorpayPayments


def build_payments(s: Settings) -> PaymentProvider:
    if s.payment_provider == "razorpay":
        return RazorpayPayments(s.razorpay_key_id, s.razorpay_key_secret, s.razorpay_webhook_secret)
    if s.is_production:
        raise RuntimeError("Mock payments are not available in production")
    return MockPayments(s.mock_payment_secret)
