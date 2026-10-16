from dataclasses import dataclass

from app.domain import Answer, Symptom, Triage
from app.screening_policy.config import PolicyConfig


@dataclass
class TriageResult:
    level: Triage
    reasons: list[str]


def triage(answers: dict[Symptom, Answer], cfg: PolicyConfig) -> TriageResult:
    """Symptom triage. 'Not sure' is treated conservatively and never as 'no'."""
    reasons: list[str] = []
    for rule in cfg.urgent_symptom_rules:
        if all(answers.get(s) == Answer.yes for s in rule):
            reasons.append("+".join(s.value for s in rule))
    if reasons:
        return TriageResult(Triage.urgent, reasons)
    caution = [s.value for s in cfg.caution_symptoms if answers.get(s) in (Answer.yes, Answer.not_sure)]
    if caution:
        return TriageResult(Triage.caution, caution)
    return TriageResult(Triage.routine, [])
