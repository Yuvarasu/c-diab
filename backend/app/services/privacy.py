import logging

from sqlalchemy import delete, select

from app.context import AppContext
from app.models import CartItem, HealthProfile, Order, Screening, utcnow
from app.services.audit import audit
from app.services.consent import latest_consents
from app.storage.base import StorageError

log = logging.getLogger("cdiab.privacy")


def export_data(db, user) -> dict:
    p = user.profile
    hp = db.get(HealthProfile, user.id)
    screenings = db.scalars(select(Screening).where(Screening.user_id == user.id).order_by(Screening.created_at)).all()
    orders = db.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.created_at)).all()
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {
        "exported_at": utcnow().isoformat(),
        "profile": {"email": p.email, "full_name": p.full_name, "phone": p.phone, "created_at": iso(p.created_at)},
        "health_profile": None if not hp else {k: getattr(hp, k) for k in (
            "diabetes_type", "diabetes_duration_years", "prior_foot_ulcer", "foot_surgery_or_amputation", "current_symptoms_note")},
        "consents": latest_consents(db, user.id),
        "screenings": [{"id": str(s.id), "created_at": iso(s.created_at), "status": s.status, "outcome": s.outcome,
                        "symptoms": s.symptoms, "is_demo": s.is_demo, "model_version": s.model_version,
                        "images": [{"side": i.side, "width": i.width, "height": i.height} for i in s.images]} for s in screenings],
        "orders": [{"id": str(o.id), "status": o.status, "total_paise": o.total_paise, "created_at": iso(o.created_at),
                    "items": [{"name": i.product_name, "size": i.size, "quantity": i.quantity} for i in o.items]} for o in orders],
    }


def delete_account(ctx: AppContext, db, user) -> None:
    """Deletes health data and images, anonymises the profile. Order and payment records are kept (legal/tax retention)."""
    for s in db.scalars(select(Screening).where(Screening.user_id == user.id)).all():
        for img in s.images:
            try:
                ctx.storage.delete(img.storage_path)
            except StorageError:
                log.warning("image object could not be deleted during account deletion")
        db.delete(s)
    db.execute(delete(CartItem).where(CartItem.user_id == user.id))
    hp = db.get(HealthProfile, user.id)
    if hp:
        db.delete(hp)
    for o in db.scalars(select(Order).where(Order.user_id == user.id)):
        o.delivery_instructions = None
    p = user.profile
    p.email = p.phone = p.date_of_birth = None
    p.full_name, p.deleted_at = "Deleted user", utcnow()
    audit(db, user.id, "account_deleted", "profile", user.id)
    db.commit()
    ctx.auth_admin.delete_user(str(user.id))
