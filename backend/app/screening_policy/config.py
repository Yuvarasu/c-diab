from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.domain import Outcome, Side, Symptom

# Invariants that no configuration can change: these outcomes never unlock footwear.
NEVER_ELIGIBLE = frozenset({Outcome.urgent_warning, Outcome.possible_deeper_wound, Outcome.inconclusive_image})


class PolicyConfig(BaseModel):
    version: str
    description: str = ""
    approved_by: Optional[str] = None
    approved_on: Optional[date] = None
    allowed_environments: list[str] = ["development", "test"]
    screening_freshness_days: int = Field(30, ge=1, le=365)
    require_clinical_review_for_purchase: bool = True
    auto_eligible_outcomes: list[Outcome] = [Outcome.no_obvious_wound, Outcome.possible_superficial_wound]
    clinician_overridable_outcomes: list[Outcome] = [Outcome.clinical_review_required]
    min_model_confidence: Optional[float] = Field(None, ge=0, le=1)
    required_image_sides: list[Side] = [Side.left, Side.right]
    urgent_symptom_rules: list[list[Symptom]]
    caution_symptoms: list[Symptom]

    @model_validator(mode="after")
    def _invariants(self):
        for name in ("auto_eligible_outcomes", "clinician_overridable_outcomes"):
            bad = NEVER_ELIGIBLE.intersection(getattr(self, name))
            if bad:
                raise ValueError(f"{name} may not contain {sorted(b.value for b in bad)}")
        if not self.urgent_symptom_rules:
            raise ValueError("urgent_symptom_rules must not be empty")
        return self

    @property
    def is_approved(self) -> bool:
        return bool(self.approved_by and self.approved_on)


def load_policy(path: str, app_env: str) -> PolicyConfig:
    p = Path(path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parents[2] / p
    cfg = PolicyConfig.model_validate_json(p.read_text(encoding="utf-8"))
    if app_env not in cfg.allowed_environments:
        raise RuntimeError(f"Policy '{cfg.version}' is not allowed in environment '{app_env}'")
    return cfg
