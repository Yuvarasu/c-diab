from dataclasses import dataclass
from typing import Optional

from app.ai.base import ModelResult
from app.domain import Outcome, Triage
from app.screening_policy.config import PolicyConfig


def determine_outcome(triage_level: Triage, quality_ok: bool, model: Optional[ModelResult], cfg: PolicyConfig) -> Outcome:
    """Server-side screening policy. Order matters: safety first, uncertainty is never 'normal'."""
    if triage_level == Triage.urgent:
        return Outcome.urgent_warning
    if not quality_ok or model is None or model.wound_detected is None:
        return Outcome.inconclusive_image
    if cfg.min_model_confidence is not None and model.confidence is not None and model.confidence < cfg.min_model_confidence:
        return Outcome.inconclusive_image
    if model.wound_detected and model.category == "deep":
        return Outcome.possible_deeper_wound
    if triage_level == Triage.caution:
        return Outcome.clinical_review_required
    if model.wound_detected and model.category == "superficial":
        return Outcome.possible_superficial_wound
    if model.wound_detected:  # wound seen but the model cannot grade it
        return Outcome.clinical_review_required
    return Outcome.no_obvious_wound


def needs_clinical_review(outcome: Outcome, cfg: PolicyConfig) -> bool:
    """Whether the case belongs in the clinician queue (purchase pathway)."""
    if outcome == Outcome.clinical_review_required:
        return True
    return cfg.require_clinical_review_for_purchase and outcome in cfg.auto_eligible_outcomes
