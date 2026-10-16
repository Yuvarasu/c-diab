from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, require_roles
from app.api.errors import ApiError
from app.domain import Role
from app.models import Order, Product, ProductVariant, Profile, Screening
from app.schemas.api import AssignIn, OrderOut, OrderStatusIn, ProductIn, ProductPatch, VariantIn, VariantPatch
from app.services import orders as order_svc
from app.services.audit import audit

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require_roles(Role.admin)


def _product(p: Product) -> dict:
    return {**{k: getattr(p, k) for k in ("id", "slug", "name", "description", "intended_use", "materials", "care_instructions",
                                          "shipping_info", "return_info", "price_paise", "image_urls", "requires_screening", "active")},
            "variants": [{"id": v.id, "size": v.size, "sku": v.sku, "stock": v.stock,
                          "price_override_paise": v.price_override_paise} for v in p.variants]}


@router.get("/products")
def products(_: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    return [_product(p) for p in db.scalars(select(Product).order_by(Product.name))]


@router.post("/products", status_code=201)
def create_product(body: ProductIn, admin: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    data = body.model_dump(exclude={"variants"})
    p = Product(**data)
    p.variants = [ProductVariant(**v.model_dump()) for v in body.variants]
    db.add(p)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "conflict", "A product with this slug or size already exists.")
    audit(db, admin.id, "product_created", "product", p.id)
    db.commit()
    return _product(p)


@router.patch("/products/{product_id}")
def patch_product(product_id: UUID, body: ProductPatch, admin: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if p is None:
        raise ApiError(404, "not_found", "Product not found.")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(p, k, v)
    audit(db, admin.id, "product_updated", "product", p.id, fields=sorted(changes))
    db.commit()
    return _product(p)


@router.post("/products/{product_id}/variants", status_code=201)
def add_variant(product_id: UUID, body: VariantIn, admin: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if p is None:
        raise ApiError(404, "not_found", "Product not found.")
    p.variants.append(ProductVariant(**body.model_dump()))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "conflict", "That size already exists for this product.")
    audit(db, admin.id, "variant_added", "product", p.id)
    db.commit()
    return _product(p)


@router.patch("/variants/{variant_id}")
def patch_variant(variant_id: UUID, body: VariantPatch, admin: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    v = db.get(ProductVariant, variant_id)
    if v is None:
        raise ApiError(404, "not_found", "Variant not found.")
    changes = body.model_dump(exclude_unset=True)
    for k, val in changes.items():
        setattr(v, k, val)
    audit(db, admin.id, "variant_updated", "variant", v.id, fields=sorted(changes))
    db.commit()
    return _product(v.product)


@router.get("/orders", response_model=list[OrderOut])
def orders(status: str | None = Query(None), limit: int = Query(50, ge=1, le=200),
           _: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    q = select(Order).order_by(Order.created_at.desc()).limit(limit)
    if status:
        q = q.where(Order.status == status)
    return [order_svc.order_out(o) for o in db.scalars(q)]


@router.put("/orders/{order_id}/status", response_model=OrderOut)
def order_status(order_id: UUID, body: OrderStatusIn, admin: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    return order_svc.order_out(order_svc.set_status(db, admin, order_id, body.status))


@router.get("/analytics")
def analytics(_: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    by_status = dict(db.execute(select(Order.status, func.count()).group_by(Order.status)).all())
    revenue = db.scalar(select(func.coalesce(func.sum(Order.total_paise), 0)).where(
        Order.status.in_(["paid", "processing", "shipped", "delivered"]))) or 0
    low = db.execute(select(Product.name, ProductVariant.size, ProductVariant.stock).join(ProductVariant)
                     .where(ProductVariant.stock <= 5).order_by(ProductVariant.stock)).all()
    return {"orders_by_status": by_status, "revenue_paise": int(revenue),
            "low_stock": [{"product": n, "size": s, "stock": k} for n, s, k in low],
            "screenings_total": db.scalar(select(func.count()).select_from(Screening)) or 0}  # counts only, no health detail


@router.get("/review-queue")
def review_queue(_: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    """Admins can route cases but never see photos, symptoms or identities."""
    rows = db.scalars(select(Screening).where(Screening.requires_clinical_review.is_(True), Screening.status == "completed")
                      .order_by(Screening.created_at))
    return [{"screening_id": s.id, "created_at": s.created_at, "outcome": s.outcome,
             "assigned_reviewer_id": s.assigned_reviewer_id, "reviewed": bool(s.reviews)} for s in rows]


@router.get("/reviewers")
def reviewers(_: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(Profile).where(Profile.role == Role.clinical_reviewer.value, Profile.deleted_at.is_(None)))
    return [{"id": r.id, "full_name": r.full_name} for r in rows]


@router.post("/screenings/{screening_id}/assign")
def assign(screening_id: UUID, body: AssignIn, admin: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    s = db.get(Screening, screening_id)
    reviewer = db.get(Profile, body.reviewer_id)
    if s is None or not s.requires_clinical_review:
        raise ApiError(404, "not_found", "Screening not found.")
    if reviewer is None or reviewer.role != Role.clinical_reviewer.value:
        raise ApiError(422, "invalid_reviewer", "The selected user is not a clinical reviewer.")
    s.assigned_reviewer_id = reviewer.id
    audit(db, admin.id, "review_assigned", "screening", s.id, reviewer_id=str(reviewer.id))
    db.commit()
    return {"screening_id": s.id, "assigned_reviewer_id": reviewer.id}
