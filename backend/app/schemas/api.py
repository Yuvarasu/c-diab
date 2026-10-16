from datetime import datetime
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domain import CURRENT_POLICY_VERSION, Answer, ConsentType, ReviewDecision, Side

Phone = Annotated[str, StringConstraints(pattern=r"^\+?[0-9]{10,13}$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class ProfileOut(BaseModel):
    id: UUID
    email: Optional[str]
    full_name: Optional[str]
    phone: Optional[str]
    role: str
    consents: dict[str, bool]
    has_health_profile: bool


class ProfilePatch(BaseModel):
    full_name: Optional[Name] = None
    phone: Optional[Phone] = None


class HealthProfileIO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    diabetes_type: Optional[Literal["type1", "type2", "gestational", "other", "not_sure"]] = None
    diabetes_duration_years: Optional[int] = Field(None, ge=0, le=80)
    prior_foot_ulcer: Optional[Answer] = None
    foot_surgery_or_amputation: Optional[Answer] = None
    current_symptoms_note: Optional[str] = Field(None, max_length=1000)


class ConsentIn(BaseModel):
    consent_type: ConsentType
    granted: bool
    policy_version: str = Field(CURRENT_POLICY_VERSION, max_length=20)


class SymptomsIn(BaseModel):
    open_wound: Answer
    redness_swelling: Answer
    unusually_warm: Answer
    discharge: Answer
    skin_color_change: Answer
    new_or_worsening_wound: Answer
    clinician_assessed: Answer = Answer.not_sure


class AnalyzeIn(BaseModel):
    screening_id: UUID


class ReviewIn(BaseModel):
    decision: ReviewDecision
    notes: Optional[str] = Field(None, max_length=2000)


class QualityIssue(BaseModel):
    code: str
    message: str


class ImageOut(BaseModel):
    id: UUID
    side: str
    url: str
    width: int
    height: int
    quality_ok: bool
    issues: list[QualityIssue]


class EligibilityOut(BaseModel):
    eligible: bool
    reason_code: str
    message: str
    screening_id: Optional[UUID] = None
    is_demo: bool = False
    policy_approved: bool = False
    clinical_review_pending: bool = False


class ClinicalReviewOut(BaseModel):
    required: bool
    status: Literal["not_required", "pending", "completed"]
    decision: Optional[str] = None


class ScreeningOut(BaseModel):
    id: UUID
    created_at: datetime
    completed_at: Optional[datetime]
    status: str
    symptoms: dict
    triage_level: str
    triage_guidance: str
    outcome: Optional[str]
    title: str
    summary: str
    next_steps: list[str]
    image_quality_ok: Optional[bool]
    quality_issues: list[QualityIssue]
    images: list[ImageOut]
    wound_detected: Optional[bool]
    category: Optional[str]
    confidence: Optional[float]
    model_name: Optional[str]
    model_version: Optional[str]
    is_demo: bool
    demo_banner: Optional[str]
    clinical_review: ClinicalReviewOut
    eligibility: EligibilityOut
    is_latest: bool
    policy_version: str
    disclaimer: str


class ScreeningSummary(BaseModel):
    id: UUID
    created_at: datetime
    status: str
    outcome: Optional[str]
    title: str
    is_demo: bool
    triage_level: str


# ---- shop ----
class VariantOut(BaseModel):
    id: UUID
    size: str
    stock_status: Literal["in_stock", "low_stock", "out_of_stock"]
    max_quantity: int


class ProductOut(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str
    intended_use: str
    materials: str
    care_instructions: str
    shipping_info: str
    return_info: str
    price_paise: int
    image_urls: list[str]
    requires_screening: bool
    in_stock: bool
    variants: list[VariantOut]


class CartPut(BaseModel):
    variant_id: UUID
    quantity: int = Field(ge=1, le=10)


class CartItemOut(BaseModel):
    variant_id: UUID
    product_id: UUID
    product_name: str
    size: str
    unit_price_paise: int
    quantity: int
    line_total_paise: int
    available: int
    in_stock: bool


class CartOut(BaseModel):
    items: list[CartItemOut]
    subtotal_paise: int
    shipping_paise: int
    total_paise: int
    has_issues: bool
    requires_screening: bool


class CheckoutIn(BaseModel):
    screening_id: Optional[UUID] = None
    idempotency_key: str = Field(min_length=8, max_length=64)
    shipping_name: Name
    shipping_phone: Phone
    address_line1: str = Field(min_length=3, max_length=200)
    address_line2: Optional[str] = Field(None, max_length=200)
    city: str = Field(min_length=2, max_length=80)
    state: str = Field(min_length=2, max_length=80)
    pincode: str = Field(pattern=r"^[1-9][0-9]{5}$")
    delivery_instructions: Optional[str] = Field(None, max_length=300)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_name: str
    size: str
    unit_price_paise: int
    quantity: int


class OrderOut(BaseModel):
    id: UUID
    status: str
    payment_status: str
    subtotal_paise: int
    shipping_paise: int
    total_paise: int
    currency: str
    shipping_name: str
    shipping_phone: str
    address: dict
    delivery_instructions: Optional[str]
    items: list[OrderItemOut]
    created_at: datetime


class PaymentSessionOut(BaseModel):
    provider: str
    provider_order_id: str
    amount_paise: int
    currency: str
    public: dict


class CheckoutOut(BaseModel):
    order: OrderOut
    payment: PaymentSessionOut


class VerifyIn(BaseModel):
    order_id: UUID
    provider_payment_id: str = Field(min_length=3, max_length=80)
    signature: str = Field(min_length=3, max_length=200)


class MockCompleteIn(BaseModel):
    order_id: UUID
    outcome: Literal["success", "failure"]


# ---- admin ----
class VariantIn(BaseModel):
    size: str = Field(min_length=1, max_length=20)
    sku: Optional[str] = Field(None, max_length=60)
    stock: int = Field(0, ge=0, le=100000)
    price_override_paise: Optional[int] = Field(None, ge=0)


class ProductIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,100}$")
    name: str = Field(min_length=2, max_length=200)
    description: str = ""
    intended_use: str = ""
    materials: str = ""
    care_instructions: str = ""
    shipping_info: str = ""
    return_info: str = ""
    price_paise: int = Field(ge=0, le=10_000_000)
    image_urls: list[str] = []
    requires_screening: bool = True
    active: bool = True
    variants: list[VariantIn] = []


class ProductPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = None
    intended_use: Optional[str] = None
    materials: Optional[str] = None
    care_instructions: Optional[str] = None
    shipping_info: Optional[str] = None
    return_info: Optional[str] = None
    price_paise: Optional[int] = Field(None, ge=0, le=10_000_000)
    image_urls: Optional[list[str]] = None
    requires_screening: Optional[bool] = None
    active: Optional[bool] = None


class VariantPatch(BaseModel):
    stock: Optional[int] = Field(None, ge=0, le=100000)
    price_override_paise: Optional[int] = Field(None, ge=0)


class OrderStatusIn(BaseModel):
    status: Literal["processing", "shipped", "delivered", "cancelled"]


class AssignIn(BaseModel):
    reviewer_id: UUID
