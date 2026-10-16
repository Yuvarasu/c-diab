import logging
import uuid
from typing import Optional

from sqlalchemy import select

from app.ai.base import InferenceError
from app.ai.quality import QualityThresholds, assess_quality
from app.api.errors import ApiError
from app.context import AppContext
from app.domain import DEMO_BANNER, Answer, Outcome, Side, Symptom, Triage
from app.models import ClinicalReview, Screening, ScreeningImage, as_utc, utcnow
from app.screening_policy.eligibility import EligibilityDecision, ReviewView, ScreeningView, evaluate_eligibility
from app.screening_policy.messages import DISCLAIMER, OUTCOME_TEXT, TRIAGE_GUIDANCE
from app.screening_policy.outcome import determine_outcome, needs_clinical_review
from app.screening_policy.triage import triage
from app.services.consent import require_screening_consents
from app.services.images import ImageRejected, process_upload
from app.storage.base import StorageError

log = logging.getLogger("cdiab.screening")


def get_owned(db, user_id, screening_id) -> Screening:
    s = db.get(Screening, screening_id)
    if s is None or s.user_id != user_id:  # same answer for "missing" and "someone else's"
        raise ApiError(404, "not_found", "Screening not found.")
    return s


def latest_screening(db, user_id) -> Optional[Screening]:
    return db.scalars(select(Screening).where(Screening.user_id == user_id, Screening.status != "failed")
                      .order_by(Screening.created_at.desc()).limit(1)).first()


def get_eligibility(ctx: AppContext, db, user_id) -> EligibilityDecision:
    s = latest_screening(db, user_id)
    view = review = None
    if s:
        view = ScreeningView(s.id, s.status, s.outcome, s.triage_level, s.is_demo, s.completed_at, s.created_at)
        r = db.scalars(select(ClinicalReview).where(ClinicalReview.screening_id == s.id)
                       .order_by(ClinicalReview.created_at.desc()).limit(1)).first()
        review = ReviewView(r.decision, r.created_at) if r else None
    return evaluate_eligibility(view, review, ctx.policy, app_env=ctx.settings.app_env,
                                allow_demo=ctx.settings.allow_demo_eligibility, now=utcnow())


def create_screening(ctx: AppContext, db, user, body) -> Screening:
    require_screening_consents(db, user.id)
    data = body.model_dump(mode="json")
    answers = {Symptom(k): Answer(v) for k, v in data.items() if k != "clinician_assessed"}
    t = triage(answers, ctx.policy)
    s = Screening(user_id=user.id, status="draft", symptoms=data, triage_level=t.level.value,
                  triage_reasons=t.reasons, policy_version=ctx.policy.version)
    db.add(s)
    db.commit()
    return s


def add_image(ctx: AppContext, db, user, screening_id, side: Side, raw: bytes) -> ScreeningImage:
    s = get_owned(db, user.id, screening_id)
    if s.status == "completed":
        raise ApiError(409, "screening_completed", "This screening is already complete. Start a new one.")
    require_screening_consents(db, user.id)
    try:
        proc = process_upload(raw, ctx.settings.max_image_bytes)
    except ImageRejected as exc:
        raise ApiError(422, exc.code, exc.message)
    quality = assess_quality(proc.image, QualityThresholds(min_blur=ctx.settings.quality_min_blur))
    path = f"{user.id}/{s.id}/{side.value}-{uuid.uuid4().hex}.jpg"  # server-generated, never client supplied
    try:
        ctx.storage.put(path, proc.data, "image/jpeg")
    except StorageError:
        raise ApiError(503, "storage_unavailable", "Could not store the photo. Please try again.")
    existing = next((i for i in s.images if i.side == side.value), None)
    old_path = existing.storage_path if existing else None
    if existing:
        existing.storage_path, existing.size_bytes, existing.width, existing.height, existing.quality = \
            path, len(proc.data), proc.width, proc.height, quality
        img = existing
    else:
        img = ScreeningImage(screening_id=s.id, user_id=user.id, side=side.value, storage_path=path,
                             size_bytes=len(proc.data), width=proc.width, height=proc.height, quality=quality)
        db.add(img)
    if s.status == "failed":
        s.status = "draft"
    db.commit()
    if old_path:
        try:
            ctx.storage.delete(old_path)
        except StorageError:
            log.warning("old image object could not be deleted")
    return img


def remove_image(ctx: AppContext, db, user, screening_id, side: Side) -> None:
    s = get_owned(db, user.id, screening_id)
    if s.status == "completed":
        raise ApiError(409, "screening_completed", "This screening is already complete.")
    img = next((i for i in s.images if i.side == side.value), None)
    if img:
        path = img.storage_path
        db.delete(img)
        db.commit()
        ctx.storage.delete(path)


def analyze(ctx: AppContext, db, user, screening_id) -> Screening:
    s = get_owned(db, user.id, screening_id)
    if s.status == "completed":
        return s
    require_screening_consents(db, user.id)
    cfg = ctx.policy
    level = Triage(s.triage_level)
    model = None
    issues: list[dict] = []
    quality_ok: Optional[bool] = None
    if level != Triage.urgent:  # urgent symptoms need no photo analysis: advise care immediately
        by_side = {i.side: i for i in s.images}
        missing = [x.value for x in cfg.required_image_sides if x.value not in by_side]
        if missing:
            raise ApiError(422, "images_missing", "Add a photo of each foot before analysis.", {"missing": missing})
        for side, img in by_side.items():
            for issue in img.quality.get("issues", []):
                issues.append({"code": issue["code"], "message": f"{side.title()} foot: {issue['message']}"})
        quality_ok = not issues
        if quality_ok:
            try:
                model = ctx.inference.analyze({Side(k): ctx.storage.get(i.storage_path) for k, i in by_side.items()})
            except (InferenceError, StorageError):
                s.status = "failed"
                db.commit()
                raise ApiError(503, "ai_unavailable",
                               "The screening service is unavailable. Your photos are saved. Please try again shortly.")
            except Exception:
                log.exception("unexpected inference failure")
                s.status = "failed"
                db.commit()
                raise ApiError(503, "ai_unavailable", "The screening service had a problem. Please try again shortly.")
    outcome = determine_outcome(level, bool(quality_ok), model, cfg)
    s.outcome = outcome.value
    s.image_quality_ok = quality_ok
    s.quality_issues = issues
    if model:
        s.wound_detected, s.category, s.confidence = model.wound_detected, model.category, model.confidence
        s.model_name, s.model_version, s.is_demo = model.model_name, model.model_version, model.is_demo
    s.requires_clinical_review = needs_clinical_review(outcome, cfg)
    s.status, s.completed_at = "completed", utcnow()
    db.commit()
    return s


def build_report(ctx: AppContext, db, s: Screening) -> dict:
    outcome = Outcome(s.outcome) if s.outcome else None
    text = OUTCOME_TEXT.get(outcome) if outcome else {
        "title": "Screening in progress", "summary": "Add photos of both feet and run the analysis to see your result.", "next_steps": []}
    latest = latest_screening(db, s.user_id)
    is_latest = bool(latest and latest.id == s.id)
    if is_latest:
        elig = get_eligibility(ctx, db, s.user_id)
    else:
        elig = EligibilityDecision(False, "historical_report",
                                   "This is a historical report. Start a new screening for current guidance.",
                                   s.id, s.is_demo, ctx.policy.is_approved)
    review = s.reviews[-1] if s.reviews else None
    return {
        "id": s.id, "created_at": s.created_at, "completed_at": s.completed_at, "status": s.status,
        "symptoms": s.symptoms, "triage_level": s.triage_level, "triage_guidance": TRIAGE_GUIDANCE[s.triage_level],
        "outcome": s.outcome, "title": text["title"], "summary": text["summary"], "next_steps": text["next_steps"],
        "image_quality_ok": s.image_quality_ok, "quality_issues": s.quality_issues or [],
        "images": [image_out(s, i) for i in s.images],
        "wound_detected": s.wound_detected, "category": s.category, "confidence": s.confidence,
        "model_name": s.model_name, "model_version": s.model_version, "is_demo": s.is_demo,
        "demo_banner": DEMO_BANNER if s.is_demo else None,
        "clinical_review": {"required": s.requires_clinical_review,
                            "status": "completed" if review else "pending" if s.requires_clinical_review else "not_required",
                            "decision": review.decision if review else None},
        "eligibility": elig.__dict__, "is_latest": is_latest, "policy_version": s.policy_version,
        "disclaimer": DISCLAIMER,
    }


def image_out(s: Screening, i: ScreeningImage) -> dict:
    return {"id": i.id, "side": i.side, "url": f"/api/v1/screenings/{s.id}/images/{i.id}/content",
            "width": i.width, "height": i.height, "quality_ok": bool(i.quality.get("ok")),
            "issues": i.quality.get("issues", [])}


def summary(s: Screening) -> dict:
    title = OUTCOME_TEXT[Outcome(s.outcome)]["title"] if s.outcome else "Screening in progress"
    return {"id": s.id, "created_at": s.created_at, "status": s.status, "outcome": s.outcome, "title": title,
            "is_demo": s.is_demo, "triage_level": s.triage_level}


def delete_screening(ctx: AppContext, db, user, screening_id) -> None:
    s = get_owned(db, user.id, screening_id)
    paths = [i.storage_path for i in s.images]
    db.delete(s)
    db.commit()
    for p in paths:
        try:
            ctx.storage.delete(p)
        except StorageError:
            log.warning("image object could not be deleted")
