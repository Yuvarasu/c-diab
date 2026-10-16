import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer,
                        String, Text, TypeDecorator, UniqueConstraint, Uuid)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class UTCDateTime(TypeDecorator):
    """timestamptz that always yields timezone-aware UTC values (SQLite would otherwise return naive ones)."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


def _id():
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _ts():
    return mapped_column(UTCDateTime(), default=utcnow)


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)  # = auth.users.id
    email: Mapped[Optional[str]] = mapped_column(String(320))
    full_name: Mapped[Optional[str]] = mapped_column(String(200))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    role: Mapped[str] = mapped_column(String(32), default="customer")
    created_at: Mapped[datetime] = _ts()
    deleted_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())


class HealthProfile(Base):
    __tablename__ = "health_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    diabetes_type: Mapped[Optional[str]] = mapped_column(String(20))
    diabetes_duration_years: Mapped[Optional[int]] = mapped_column(Integer)
    prior_foot_ulcer: Mapped[Optional[str]] = mapped_column(String(10))
    foot_surgery_or_amputation: Mapped[Optional[str]] = mapped_column(String(10))
    current_symptoms_note: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = _ts()


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    consent_type: Mapped[str] = mapped_column(String(40))
    granted: Mapped[bool] = mapped_column(Boolean)
    policy_version: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = _ts()


class Screening(Base):
    __tablename__ = "screenings"
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    symptoms: Mapped[dict] = mapped_column(JSONType, default=dict)
    triage_level: Mapped[str] = mapped_column(String(16))
    triage_reasons: Mapped[list] = mapped_column(JSONType, default=list)
    outcome: Mapped[Optional[str]] = mapped_column(String(40))
    image_quality_ok: Mapped[Optional[bool]] = mapped_column(Boolean)
    quality_issues: Mapped[list] = mapped_column(JSONType, default=list)
    wound_detected: Mapped[Optional[bool]] = mapped_column(Boolean)
    category: Mapped[Optional[str]] = mapped_column(String(20))
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    model_name: Mapped[Optional[str]] = mapped_column(String(80))
    model_version: Mapped[Optional[str]] = mapped_column(String(40))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_clinical_review: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_reviewer_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="SET NULL"))
    policy_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = _ts()
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    images: Mapped[list["ScreeningImage"]] = relationship(back_populates="screening", cascade="all, delete-orphan")
    reviews: Mapped[list["ClinicalReview"]] = relationship(cascade="all, delete-orphan", order_by="ClinicalReview.created_at")


class ScreeningImage(Base):
    __tablename__ = "screening_images"
    __table_args__ = (UniqueConstraint("screening_id", "side"),)
    id: Mapped[uuid.UUID] = _id()
    screening_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("screenings.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    side: Mapped[str] = mapped_column(String(8))
    storage_path: Mapped[str] = mapped_column(String(300))
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    quality: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = _ts()
    screening: Mapped[Screening] = relationship(back_populates="images")


class ClinicalReview(Base):
    __tablename__ = "clinical_reviews"
    id: Mapped[uuid.UUID] = _id()
    screening_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("screenings.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id"))
    decision: Mapped[str] = mapped_column(String(40))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("price_paise >= 0"),)
    id: Mapped[uuid.UUID] = _id()
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    intended_use: Mapped[str] = mapped_column(Text, default="")
    materials: Mapped[str] = mapped_column(Text, default="")
    care_instructions: Mapped[str] = mapped_column(Text, default="")
    shipping_info: Mapped[str] = mapped_column(Text, default="")
    return_info: Mapped[str] = mapped_column(Text, default="")
    price_paise: Mapped[int] = mapped_column(Integer)
    image_urls: Mapped[list] = mapped_column(JSONType, default=list)
    requires_screening: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    variants: Mapped[list["ProductVariant"]] = relationship(back_populates="product", cascade="all, delete-orphan",
                                                            order_by="ProductVariant.size")


class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("product_id", "size"), CheckConstraint("stock >= 0"))
    id: Mapped[uuid.UUID] = _id()
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("products.id", ondelete="CASCADE"), index=True)
    size: Mapped[str] = mapped_column(String(20))
    sku: Mapped[Optional[str]] = mapped_column(String(60))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    price_override_paise: Mapped[Optional[int]] = mapped_column(Integer)
    product: Mapped[Product] = relationship(back_populates="variants")


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("user_id", "variant_id"), CheckConstraint("quantity > 0"))
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("product_variants.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = _ts()
    variant: Mapped[ProductVariant] = relationship()


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id"), index=True)
    screening_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("screenings.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), default="pending_payment")
    subtotal_paise: Mapped[int] = mapped_column(Integer)
    shipping_paise: Mapped[int] = mapped_column(Integer)
    total_paise: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    shipping_name: Mapped[str] = mapped_column(String(120))
    shipping_phone: Mapped[str] = mapped_column(String(20))
    address: Mapped[dict] = mapped_column(JSONType, default=dict)
    delivery_instructions: Mapped[Optional[str]] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order", order_by="Payment.created_at")


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[uuid.UUID] = _id()
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("product_variants.id", ondelete="SET NULL"))
    product_name: Mapped[str] = mapped_column(String(200))
    size: Mapped[str] = mapped_column(String(20))
    unit_price_paise: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    order: Mapped[Order] = relationship(back_populates="items")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("provider", "provider_payment_id"),)
    id: Mapped[uuid.UUID] = _id()
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    provider_order_id: Mapped[str] = mapped_column(String(80), index=True)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default="created")
    amount_paise: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    order: Mapped[Order] = relationship(back_populates="payments")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)
    id: Mapped[uuid.UUID] = _id()
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[Optional[str]] = mapped_column(String(80))
    meta: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = _ts()
