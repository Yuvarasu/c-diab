from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_user, get_ctx, get_db
from app.context import AppContext
from app.models import HealthProfile, utcnow
from app.schemas.api import ConsentIn, HealthProfileIO, ProfileOut, ProfilePatch
from app.services import privacy
from app.domain import ConsentType
from app.services.consent import latest_consents, record_consent, require_consent

router = APIRouter(prefix="/me", tags=["me"])


def _profile_out(db: Session, user: Principal) -> dict:
    p = user.profile
    return {"id": p.id, "email": p.email, "full_name": p.full_name, "phone": p.phone, "role": p.role,
            "consents": latest_consents(db, p.id), "has_health_profile": db.get(HealthProfile, p.id) is not None}


@router.get("", response_model=ProfileOut)
def get_me(user: Principal = Depends(current_user), db: Session = Depends(get_db)):
    return _profile_out(db, user)


@router.patch("", response_model=ProfileOut)
def patch_me(body: ProfilePatch, user: Principal = Depends(current_user), db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(user.profile, k, v)
    db.commit()
    return _profile_out(db, user)


@router.get("/health-profile", response_model=HealthProfileIO)
def get_health(user: Principal = Depends(current_user), db: Session = Depends(get_db)):
    return db.get(HealthProfile, user.id) or HealthProfileIO()


@router.put("/health-profile", response_model=HealthProfileIO)
def put_health(body: HealthProfileIO, user: Principal = Depends(current_user), db: Session = Depends(get_db)):
    require_consent(db, user.id, ConsentType.health_data_processing)  # health details are only stored with consent
    hp = db.get(HealthProfile, user.id) or HealthProfile(user_id=user.id)
    for k, v in body.model_dump().items():
        setattr(hp, k, v.value if hasattr(v, "value") else v)
    hp.updated_at = utcnow()
    db.add(hp)
    db.commit()
    return hp


@router.get("/consents")
def get_consents(user: Principal = Depends(current_user), db: Session = Depends(get_db)):
    return latest_consents(db, user.id)


@router.post("/consents")
def post_consent(body: ConsentIn, user: Principal = Depends(current_user), db: Session = Depends(get_db)):
    record_consent(db, user.id, body.consent_type, body.granted, body.policy_version)
    return latest_consents(db, user.id)


@router.get("/data-export")
def data_export(user: Principal = Depends(current_user), db: Session = Depends(get_db)):
    return privacy.export_data(db, user)


@router.delete("", status_code=204)
def delete_me(user: Principal = Depends(current_user), db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx)):
    privacy.delete_account(ctx, db, user)
    return Response(status_code=204)
