from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.ai.base import ModelResult
from app.domain import Answer, Outcome, ReviewDecision, Symptom, Triage
from app.screening_policy.config import NEVER_ELIGIBLE, PolicyConfig, load_policy
from app.screening_policy.eligibility import ReviewView, ScreeningView, evaluate_eligibility
from app.screening_policy.outcome import determine_outcome, needs_clinical_review
from app.screening_policy.triage import triage

NOW = datetime.now(timezone.utc)
STRICT = load_policy("policy/policy.default.json", "test")
DEMO = load_policy("policy/policy.demo.json", "test")


def answers(**kw):
    base = {s: Answer.no for s in Symptom}
    base.update({Symptom(k): Answer(v) for k, v in kw.items()})
    return base


def model(detected, category=None, demo=False):
    return ModelResult(detected, category, None, "m", "1", demo)


def view(outcome, *, status="completed", triage_level="routine", demo=False, age_days=1):
    t = NOW - timedelta(days=age_days)
    return ScreeningView(uuid4(), status, outcome.value if outcome else None, triage_level, demo, t, t)


def elig(s, review=None, cfg=DEMO, env="test", allow_demo=True):
    return evaluate_eligibility(s, review, cfg, app_env=env, allow_demo=allow_demo, now=NOW)


# ---- triage ----
def test_all_no_is_routine():
    assert triage(answers(), STRICT).level == Triage.routine


@pytest.mark.parametrize("kw", [dict(discharge="yes"), dict(open_wound="yes", redness_swelling="yes"),
                                dict(open_wound="yes", unusually_warm="yes"), dict(open_wound="yes", skin_color_change="yes"),
                                dict(new_or_worsening_wound="yes", redness_swelling="yes")])
def test_urgent_combinations(kw):
    assert triage(answers(**kw), STRICT).level == Triage.urgent


def test_not_sure_is_never_treated_as_no():
    assert triage(answers(open_wound="not_sure"), STRICT).level == Triage.caution


def test_single_yes_without_urgent_rule_is_caution():
    assert triage(answers(skin_color_change="yes"), STRICT).level == Triage.caution


# ---- outcome ----
def test_urgent_beats_everything_even_bad_photos():
    assert determine_outcome(Triage.urgent, False, None, STRICT) == Outcome.urgent_warning
    assert determine_outcome(Triage.urgent, True, model(False), STRICT) == Outcome.urgent_warning


def test_unusable_photos_or_model_are_inconclusive_never_normal():
    assert determine_outcome(Triage.routine, False, model(False), STRICT) == Outcome.inconclusive_image
    assert determine_outcome(Triage.routine, True, None, STRICT) == Outcome.inconclusive_image
    assert determine_outcome(Triage.routine, True, model(None), STRICT) == Outcome.inconclusive_image


def test_low_confidence_is_inconclusive_when_policy_sets_a_floor():
    cfg = STRICT.model_copy(update={"min_model_confidence": 0.8})
    low = ModelResult(False, None, 0.4, "m", "1", False)
    assert determine_outcome(Triage.routine, True, low, cfg) == Outcome.inconclusive_image


def test_deeper_wound_and_caution_mapping():
    assert determine_outcome(Triage.routine, True, model(True, "deep"), STRICT) == Outcome.possible_deeper_wound
    assert determine_outcome(Triage.caution, True, model(False), STRICT) == Outcome.clinical_review_required
    assert determine_outcome(Triage.routine, True, model(True, "superficial"), STRICT) == Outcome.possible_superficial_wound
    assert determine_outcome(Triage.routine, True, model(True, None), STRICT) == Outcome.clinical_review_required
    assert determine_outcome(Triage.routine, True, model(False), STRICT) == Outcome.no_obvious_wound


def test_review_queue_rules():
    assert needs_clinical_review(Outcome.clinical_review_required, DEMO)
    assert needs_clinical_review(Outcome.no_obvious_wound, STRICT)
    assert not needs_clinical_review(Outcome.no_obvious_wound, DEMO)


# ---- eligibility ----
@pytest.mark.parametrize("outcome", sorted(NEVER_ELIGIBLE))
@pytest.mark.parametrize("cfg", [STRICT, DEMO])
def test_never_eligible_outcomes_cannot_be_unlocked_even_by_clinician_approval(outcome, cfg):
    approved = ReviewView(ReviewDecision.approved_for_footwear, NOW)
    assert not elig(view(outcome), approved, cfg).eligible
    assert not elig(view(outcome), None, cfg).eligible


def test_config_cannot_make_blocked_outcomes_eligible():
    with pytest.raises(ValueError):
        PolicyConfig(version="x", urgent_symptom_rules=[[Symptom.discharge]], caution_symptoms=[],
                     auto_eligible_outcomes=[Outcome.possible_deeper_wound])
    with pytest.raises(ValueError):
        PolicyConfig(version="x", urgent_symptom_rules=[[Symptom.discharge]], caution_symptoms=[],
                     clinician_overridable_outcomes=[Outcome.inconclusive_image])


def test_missing_incomplete_and_expired_screenings_block():
    assert elig(None).reason_code == "screening_required"
    assert elig(view(None, status="draft")).reason_code == "screening_incomplete"
    assert elig(view(Outcome.no_obvious_wound, age_days=31)).reason_code == "screening_expired"


def test_strict_policy_requires_clinician_approval_for_any_purchase():
    s = view(Outcome.no_obvious_wound)
    d = elig(s, None, STRICT)
    assert not d.eligible and d.reason_code == "clinical_review_pending"
    assert elig(s, ReviewView(ReviewDecision.approved_for_footwear, NOW), STRICT).eligible


def test_clinician_decline_blocks():
    s = view(Outcome.clinical_review_required)
    for dec in (ReviewDecision.not_suitable, ReviewDecision.needs_in_person_assessment):
        assert elig(s, ReviewView(dec, NOW), DEMO).reason_code == "clinical_review_declined"


def test_clinical_review_required_outcome_needs_approval_even_in_demo_policy():
    s = view(Outcome.clinical_review_required)
    assert elig(s, None, DEMO).reason_code == "clinical_review_pending"
    assert elig(s, ReviewView(ReviewDecision.approved_for_footwear, NOW), DEMO).eligible


def test_demo_results_do_not_unlock_unless_explicitly_allowed():
    s = view(Outcome.no_obvious_wound, demo=True)
    assert elig(s, allow_demo=False).reason_code == "demo_result_not_eligible"
    d = elig(s, allow_demo=True)
    assert d.eligible and d.is_demo and "DEMO" in d.message


def test_production_requires_clinically_approved_policy():
    s = view(Outcome.no_obvious_wound)
    assert elig(s, None, STRICT, env="production").reason_code == "policy_not_clinically_approved"
    approved = STRICT.model_copy(update={"approved_by": "Dr Example", "approved_on": NOW.date(),
                                         "require_clinical_review_for_purchase": False})
    assert elig(s, None, approved, env="production").eligible


def test_demo_policy_is_refused_in_production_and_preview():
    for env in ("production", "preview"):
        with pytest.raises(RuntimeError):
            load_policy("policy/policy.demo.json", env)
