from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_ctx, get_db, require_roles
from app.api.errors import ApiError
from app.context import AppContext
from app.domain import Role
from app.models import ClinicalReview, Screening
from app.schemas.api import ReviewIn
from app.services import screenings as svc
from app.services.audit import audit
from app.storage.base import StorageError

router = APIRouter(prefix="/clinical", tags=["clinical"])
reviewer_only = require_roles(Role.clinical_reviewer)


def _assigned(db: Session, reviewer: Principal, screening_id: UUID) -> Screening:
    s = db.get(Screening, screening_id)
    if s is None or s.assigned_reviewer_id != reviewer.id:  # only records assigned to this reviewer exist for them
        raise ApiError(404, "not_found", "Screening not found.")
    return s


@router.get("/queue")
def queue(reviewer: Principal = Depends(reviewer_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(Screening).where(Screening.assigned_reviewer_id == reviewer.id).order_by(Screening.created_at))
    return [{"screening_id": s.id, "reference": str(s.id)[:8], "created_at": s.created_at, "outcome": s.outcome,
             "reviewed": bool(s.reviews)} for s in rows]


@router.get("/screenings/{screening_id}")
def detail(screening_id: UUID, reviewer: Principal = Depends(reviewer_only), db: Session = Depends(get_db)):
    s = _assigned(db, reviewer, screening_id)
    audit(db, reviewer.id, "clinical_record_viewed", "screening", s.id)
    db.commit()
    return {"screening_id": s.id, "reference": str(s.id)[:8], "created_at": s.created_at, "outcome": s.outcome,
            "symptoms": s.symptoms, "triage_level": s.triage_level, "is_demo": s.is_demo, "model_version": s.model_version,
            "images": [{"id": i.id, "side": i.side, "url": f"/api/v1/clinical/screenings/{s.id}/images/{i.id}/content"} for i in s.images],
            "reviews": [{"decision": r.decision, "notes": r.notes, "created_at": r.created_at} for r in s.reviews]}


@router.get("/screenings/{screening_id}/images/{image_id}/content")
def image(screening_id: UUID, image_id: UUID, reviewer: Principal = Depends(reviewer_only), db: Session = Depends(get_db),
          ctx: AppContext = Depends(get_ctx)):
    s = _assigned(db, reviewer, screening_id)
    img = next((i for i in s.images if i.id == image_id), None)
    if img is None:
        raise ApiError(404, "not_found", "Image not found.")
    try:
        data = ctx.storage.get(img.storage_path)
    except StorageError:
        raise ApiError(404, "not_found", "Image not found.")
    audit(db, reviewer.id, "clinical_image_viewed", "screening_image", img.id)
    db.commit()
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@router.post("/screenings/{screening_id}/review", status_code=201)
def review(screening_id: UUID, body: ReviewIn, reviewer: Principal = Depends(reviewer_only), db: Session = Depends(get_db)):
    s = _assigned(db, reviewer, screening_id)
    if s.status != "completed":
        raise ApiError(409, "screening_incomplete", "Only completed screenings can be reviewed.")
    db.add(ClinicalReview(screening_id=s.id, reviewer_id=reviewer.id, decision=body.decision.value, notes=body.notes))
    audit(db, reviewer.id, "clinical_review_submitted", "screening", s.id, decision=body.decision.value)
    db.commit()
    return {"screening_id": s.id, "decision": body.decision.value}
