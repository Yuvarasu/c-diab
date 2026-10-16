from enum import StrEnum

DEMO_BANNER = "DEMO RESULT — NOT A MEDICAL ASSESSMENT"
CURRENT_POLICY_VERSION = "2026-10-10"


class Role(StrEnum):
    customer = "customer"
    admin = "admin"
    clinical_reviewer = "clinical_reviewer"


class ConsentType(StrEnum):
    terms = "terms"
    health_data_processing = "health_data_processing"
    image_screening = "image_screening"
    ai_training = "ai_training"  # optional, always separate from the others


REQUIRED_FOR_SCREENING = (ConsentType.health_data_processing, ConsentType.image_screening)


class Answer(StrEnum):
    yes = "yes"
    no = "no"
    not_sure = "not_sure"


class Symptom(StrEnum):
    open_wound = "open_wound"
    redness_swelling = "redness_swelling"
    unusually_warm = "unusually_warm"
    discharge = "discharge"
    skin_color_change = "skin_color_change"
    new_or_worsening_wound = "new_or_worsening_wound"


class Triage(StrEnum):
    routine = "routine"
    caution = "caution"
    urgent = "urgent"


class Outcome(StrEnum):
    no_obvious_wound = "no_obvious_wound"
    possible_superficial_wound = "possible_superficial_wound"
    possible_deeper_wound = "possible_deeper_wound"
    inconclusive_image = "inconclusive_image"
    clinical_review_required = "clinical_review_required"
    urgent_warning = "urgent_warning"


class ScreeningStatus(StrEnum):
    draft = "draft"
    completed = "completed"
    failed = "failed"


class Side(StrEnum):
    left = "left"
    right = "right"


class ReviewDecision(StrEnum):
    approved_for_footwear = "approved_for_footwear"
    not_suitable = "not_suitable"
    needs_in_person_assessment = "needs_in_person_assessment"


class OrderStatus(StrEnum):
    pending_payment = "pending_payment"
    payment_failed = "payment_failed"
    paid = "paid"
    processing = "processing"
    shipped = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"


class PaymentStatus(StrEnum):
    created = "created"
    paid = "paid"
    failed = "failed"
