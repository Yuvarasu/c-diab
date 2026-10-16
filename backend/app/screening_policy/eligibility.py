from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from app.domain import Outcome, ReviewDecision, ScreeningStatus, Triage
from app.models import as_utc
from app.screening_policy.config import NEVER_ELIGIBLE, PolicyConfig


@dataclass
class ScreeningView:
    id: UUID
    status: str
    outcome: Optional[str]
    triage_level: str
    is_demo: bool
    completed_at: Optional[datetime]
    created_at: datetime


@dataclass
class ReviewView:
    decision: str
    created_at: datetime


@dataclass
class EligibilityDecision:
    eligible: bool
    reason_code: str
    message: str
    screening_id: Optional[UUID] = None
    is_demo: bool = False
    policy_approved: bool = False
    clinical_review_pending: bool = False


def evaluate_eligibility(screening: Optional[ScreeningView], review: Optional[ReviewView], cfg: PolicyConfig, *,
                         app_env: str, allow_demo: bool, now: datetime) -> EligibilityDecision:
    """Whether therapeutic footwear may be purchased. Pure function; every rule is enforced server side."""
    def no(code: str, msg: str, **kw) -> EligibilityDecision:
        return EligibilityDecision(False, code, msg, screening.id if screening else None,
                                   bool(screening and screening.is_demo), cfg.is_approved, **kw)

    if app_env == "production" and not cfg.is_approved:
        return no("policy_not_clinically_approved",
                  "Therapeutic footwear purchases are paused until the screening policy has been approved by a qualified healthcare professional.")
    if screening is None:
        return no("screening_required", "Complete a foot screening before buying therapeutic footwear.")
    if screening.status != ScreeningStatus.completed:
        return no("screening_incomplete", "Finish your foot screening (add both photos and run the analysis) first.")
    if screening.triage_level == Triage.urgent or screening.outcome == Outcome.urgent_warning:
        return no("urgent_warning", "Your answers suggest warning signs. Please get medical assessment first. Footwear purchase is paused.")
    if screening.outcome is None or Outcome(screening.outcome) in NEVER_ELIGIBLE:
        return no("outcome_not_eligible",
                  "Your screening result needs professional assessment or new photos before footwear can be offered.")
    completed = as_utc(screening.completed_at or screening.created_at)
    if now - completed > timedelta(days=cfg.screening_freshness_days):
        return no("screening_expired", f"Your screening is older than {cfg.screening_freshness_days} days. Please repeat it.")
    if screening.is_demo and not allow_demo:
        return no("demo_result_not_eligible", "Demo results cannot unlock purchases in this configuration.")

    outcome = Outcome(screening.outcome)
    if review and review.decision != ReviewDecision.approved_for_footwear:
        return no("clinical_review_declined",
                  "A clinician reviewed your screening and did not approve footwear. Please follow their advice.")
    needs_review = outcome == Outcome.clinical_review_required or cfg.require_clinical_review_for_purchase
    if needs_review:
        if review and review.decision == ReviewDecision.approved_for_footwear and outcome in cfg.clinician_overridable_outcomes:
            pass
        else:
            return no("clinical_review_pending", "A clinician must review your screening before footwear can be offered.",
                      clinical_review_pending=True)
    elif outcome not in cfg.auto_eligible_outcomes:
        return no("outcome_not_eligible", "Your screening result does not qualify for footwear purchase.")

    note = " (DEMO result: for demonstration only)" if screening.is_demo else ""
    return EligibilityDecision(True, "eligible", "You can continue to purchase" + note + ".", screening.id,
                               screening.is_demo, cfg.is_approved)
