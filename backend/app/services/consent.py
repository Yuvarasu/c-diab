from sqlalchemy import select

from app.api.errors import ApiError
from app.domain import REQUIRED_FOR_SCREENING, ConsentType
from app.models import ConsentRecord


def latest_consents(db, user_id) -> dict[str, bool]:
    rows = db.scalars(select(ConsentRecord).where(ConsentRecord.user_id == user_id).order_by(ConsentRecord.created_at))
    out: dict[str, bool] = {}
    for r in rows:
        out[r.consent_type] = r.granted
    return out


def record_consent(db, user_id, ctype: ConsentType, granted: bool, version: str) -> None:
    db.add(ConsentRecord(user_id=user_id, consent_type=ctype.value, granted=granted, policy_version=version))
    db.commit()


def require_screening_consents(db, user_id) -> None:
    have = latest_consents(db, user_id)
    missing = [c.value for c in REQUIRED_FOR_SCREENING if not have.get(c.value)]
    if missing:
        raise ApiError(403, "consent_required", "Consent is required before health information or photos are processed.",
                       {"missing": missing})


def require_consent(db, user_id, ctype: ConsentType) -> None:
    if not latest_consents(db, user_id).get(ctype.value):
        raise ApiError(403, "consent_required", "Consent is required before this health information is processed.",
                       {"missing": [ctype.value]})
