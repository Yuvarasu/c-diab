from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_user, get_ctx, get_db, limit
from app.api.errors import ApiError
from app.context import AppContext
from app.domain import Side
from app.models import Screening
from app.schemas.api import AnalyzeIn, EligibilityOut, ImageOut, ScreeningOut, ScreeningSummary, SymptomsIn
from app.services import screenings as svc
from app.storage.base import StorageError

router = APIRouter(prefix="/screenings", tags=["screenings"])


@router.post("", response_model=ScreeningOut, status_code=201)
def create(body: SymptomsIn, user: Principal = Depends(current_user), db: Session = Depends(get_db),
           ctx: AppContext = Depends(get_ctx)):
    return svc.build_report(ctx, db, svc.create_screening(ctx, db, user, body))


@router.get("", response_model=list[ScreeningSummary])
def history(limit_: int = Query(20, ge=1, le=100, alias="limit"), user: Principal = Depends(current_user),
            db: Session = Depends(get_db)):
    rows = db.scalars(select(Screening).where(Screening.user_id == user.id).order_by(Screening.created_at.desc()).limit(limit_))
    return [svc.summary(s) for s in rows]


@router.get("/eligibility", response_model=EligibilityOut)
def eligibility(user: Principal = Depends(current_user), db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx)):
    return svc.get_eligibility(ctx, db, user.id).__dict__


@router.post("/analyze", response_model=ScreeningOut, dependencies=[Depends(limit("analyze", 15, 3600))])
def analyze(body: AnalyzeIn, user: Principal = Depends(current_user), db: Session = Depends(get_db),
            ctx: AppContext = Depends(get_ctx)):
    return svc.build_report(ctx, db, svc.analyze(ctx, db, user, body.screening_id))


@router.get("/{screening_id}", response_model=ScreeningOut)
def detail(screening_id: UUID, user: Principal = Depends(current_user), db: Session = Depends(get_db),
           ctx: AppContext = Depends(get_ctx)):
    return svc.build_report(ctx, db, svc.get_owned(db, user.id, screening_id))


@router.delete("/{screening_id}", status_code=204)
def delete(screening_id: UUID, user: Principal = Depends(current_user), db: Session = Depends(get_db),
           ctx: AppContext = Depends(get_ctx)):
    svc.delete_screening(ctx, db, user, screening_id)
    return Response(status_code=204)


@router.post("/{screening_id}/images", response_model=ImageOut, status_code=201,
             dependencies=[Depends(limit("upload", 40, 3600))])
def upload(screening_id: UUID, side: Side = Form(...), file: UploadFile = File(...),
           user: Principal = Depends(current_user), db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx)):
    raw = file.file.read(ctx.settings.max_image_bytes + 1)  # never buffer more than the limit
    img = svc.add_image(ctx, db, user, screening_id, side, raw)
    s = svc.get_owned(db, user.id, screening_id)
    return svc.image_out(s, img)


@router.delete("/{screening_id}/images/{side}", status_code=204)
def remove(screening_id: UUID, side: Side, user: Principal = Depends(current_user), db: Session = Depends(get_db),
           ctx: AppContext = Depends(get_ctx)):
    svc.remove_image(ctx, db, user, screening_id, side)
    return Response(status_code=204)


@router.get("/{screening_id}/images/{image_id}/content")
def image_content(screening_id: UUID, image_id: UUID, user: Principal = Depends(current_user),
                  db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx)):
    s = svc.get_owned(db, user.id, screening_id)
    img = next((i for i in s.images if i.id == image_id), None)
    if img is None:
        raise ApiError(404, "not_found", "Image not found.")
    try:
        data = ctx.storage.get(img.storage_path)
    except StorageError:
        raise ApiError(404, "not_found", "Image not found.")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})
