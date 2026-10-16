from io import BytesIO

import pytest
from PIL import Image

from app.ai.base import InferenceError
from app.domain import DEMO_BANNER
from app.storage.base import StorageError
from app.tests.conftest import API, NO, User, dark_jpeg, flat_jpeg, sharp_jpeg


def test_consent_is_required_before_any_screening(alice):
    r = alice.post(f"{API}/screenings", json=NO)
    assert r.status_code == 403 and r.json()["error"]["code"] == "consent_required"
    alice.consent("health_data_processing")  # one of two is still not enough
    assert alice.post(f"{API}/screenings", json=NO).status_code == 403


def test_withdrawing_consent_blocks_further_processing(alice):
    alice.consent()
    sid = alice.post(f"{API}/screenings", json=NO).json()["id"]
    alice.post(f"{API}/me/consents", json={"consent_type": "image_screening", "granted": False})
    assert alice.upload(sid, "left", sharp_jpeg()).status_code == 403


def test_ai_training_consent_is_separate_and_optional(alice):
    alice.consent()  # the two screening consents only
    assert alice.get(f"{API}/me/consents").json().get("ai_training") is None
    assert alice.post(f"{API}/screenings", json=NO).status_code == 201


def test_full_flow_returns_labelled_demo_result(alice):
    rep = alice.screen()
    assert rep["status"] == "completed" and rep["outcome"] == "no_obvious_wound"
    assert rep["is_demo"] is True and rep["demo_banner"] == DEMO_BANNER == "DEMO RESULT — NOT A MEDICAL ASSESSMENT"
    assert rep["confidence"] is None  # the demo never invents a confidence
    assert rep["model_version"] == "demo-0" and "not a medical diagnosis" in rep["disclaimer"]
    assert "does not rule out" in rep["summary"] and len(rep["images"]) == 2


def test_mock_result_cannot_be_mistaken_for_real(make_app):
    client, _ = make_app(demo_force_outcome="superficial")
    u = User(client)
    rep = u.screen()
    assert rep["is_demo"] and rep["demo_banner"] and rep["outcome"] == "possible_superficial_wound"
    summary = u.get(f"{API}/screenings").json()[0]
    assert summary["is_demo"] is True


@pytest.mark.parametrize("forced,outcome", [("deep", "possible_deeper_wound"), ("undetermined", "inconclusive_image"),
                                            ("superficial", "possible_superficial_wound")])
def test_model_outputs_map_to_outcomes(make_app, forced, outcome):
    client, _ = make_app(demo_force_outcome=forced)
    assert User(client).screen()["outcome"] == outcome


def test_deeper_wound_gives_warning_not_a_treatment_recommendation(make_app):
    client, _ = make_app(demo_force_outcome="deep")
    rep = User(client).screen()
    text = (rep["summary"] + " ".join(rep["next_steps"])).lower()
    assert "professional" in text or "doctor" in text
    assert "not presented as suitable" in text and rep["eligibility"]["eligible"] is False


def test_poor_photos_give_inconclusive_never_normal(alice):
    rep = alice.screen(left=flat_jpeg(), right=dark_jpeg())
    assert rep["outcome"] == "inconclusive_image" and rep["image_quality_ok"] is False
    codes = {i["code"] for i in rep["quality_issues"]}
    assert {"blurry", "too_dark"} <= codes
    assert rep["wound_detected"] is None and rep["eligibility"]["eligible"] is False
    assert "NOT a normal result" in rep["summary"]


def test_missing_photos_ask_for_them_instead_of_guessing(alice):
    alice.consent()
    sid = alice.post(f"{API}/screenings", json=NO).json()["id"]
    alice.upload(sid, "left", sharp_jpeg())
    r = alice.post(f"{API}/screenings/analyze", json={"screening_id": sid})
    assert r.status_code == 422 and r.json()["error"]["details"]["missing"] == ["right"]


def test_urgent_symptoms_are_flagged_immediately_and_need_no_photos(alice):
    alice.consent()
    r = alice.post(f"{API}/screenings", json={**NO, "discharge": "yes"})
    body = r.json()
    assert r.status_code == 201 and body["triage_level"] == "urgent" and "urgent medical" in body["triage_guidance"]
    rep = alice.post(f"{API}/screenings/analyze", json={"screening_id": body["id"]}).json()
    assert rep["outcome"] == "urgent_warning" and rep["eligibility"]["eligible"] is False
    assert rep["is_demo"] is False  # rule-based safety advice is not a simulated result


def test_caution_symptoms_require_clinical_review(alice):
    rep = alice.screen(symptoms={"open_wound": "not_sure"})
    assert rep["triage_level"] == "caution" and rep["outcome"] == "clinical_review_required"
    assert rep["clinical_review"] == {"required": True, "status": "pending", "decision": None}
    assert rep["eligibility"]["reason_code"] == "clinical_review_pending"


def test_ai_service_failure_is_safe_and_retryable(ctx, alice):
    class Down:
        name = "down"

        def analyze(self, images):
            raise InferenceError("down")
    good = ctx.inference
    ctx.inference = Down()
    rep = alice.screen(analyze=False)
    r = alice.post(f"{API}/screenings/analyze", json={"screening_id": rep["id"]})
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_unavailable"
    assert alice.get(f"{API}/screenings/{rep['id']}").json()["status"] == "failed"
    assert alice.get(f"{API}/screenings/eligibility").json()["eligible"] is False
    ctx.inference = good  # service recovers: same screening can be analysed again
    assert alice.post(f"{API}/screenings/analyze", json={"screening_id": rep["id"]}).status_code == 200


def test_unexpected_model_crash_is_also_a_safe_503(ctx, alice):
    class Crash:
        name = "crash"

        def analyze(self, images):
            raise ZeroDivisionError("bug")
    ctx.inference = Crash()
    sid = alice.screen(analyze=False)["id"]
    assert alice.post(f"{API}/screenings/analyze", json={"screening_id": sid}).status_code == 503


def test_users_cannot_see_or_touch_other_users_screenings_or_images(alice, bob):
    rep = alice.screen()
    sid, img = rep["id"], rep["images"][0]
    bob.consent()
    assert alice.get(f"{API}/screenings/{sid}").status_code == 200
    for r in (bob.get(f"{API}/screenings/{sid}"), bob.delete(f"{API}/screenings/{sid}"),
              bob.post(f"{API}/screenings/analyze", json={"screening_id": sid}),
              bob.upload(sid, "left", sharp_jpeg()),
              bob.delete(f"{API}/screenings/{sid}/images/left"),
              bob.get(img["url"])):
        assert r.status_code == 404, r.request.url
    assert bob.get(f"{API}/screenings").json() == []
    assert alice.get(img["url"]).status_code == 200
    assert bob.get(f"{API}/screenings/eligibility").json()["reason_code"] == "screening_required"


def test_images_require_authentication(client, alice):
    url = alice.screen()["images"][0]["url"]
    assert client.get(url).status_code == 401


def test_client_cannot_choose_storage_paths(ctx, alice):
    rep = alice.screen()
    with ctx.session_factory() as db:
        from app.models import ScreeningImage
        paths = [i.storage_path for i in db.query(ScreeningImage).all()]
    assert all(p.startswith(f"{alice.id}/{rep['id']}/") for p in paths)


def test_upload_rejects_non_images_even_with_image_content_type(alice):
    alice.consent()
    sid = alice.post(f"{API}/screenings", json=NO).json()["id"]
    r = alice.upload(sid, "left", b"<html>not an image</html>", "x.jpg", "image/jpeg")
    assert r.status_code == 422 and r.json()["error"]["code"] == "unsupported_image"
    assert alice.upload(sid, "left", b"", "x.jpg").status_code == 422


def test_upload_rejects_wrong_format_oversize_and_tiny_images(make_app):
    client, _ = make_app(max_image_bytes=50_000)
    u = User(client)
    u.consent()
    sid = u.post(f"{API}/screenings", json=NO).json()["id"]
    assert u.upload(sid, "left", sharp_jpeg()).json()["error"]["code"] == "file_too_large"
    buf = BytesIO()
    Image.new("RGB", (100, 100), (200, 10, 10)).save(buf, "GIF")
    assert u.upload(sid, "left", buf.getvalue()).json()["error"]["code"] == "unsupported_image"
    tiny = BytesIO()
    Image.new("RGB", (100, 100), (200, 10, 10)).save(tiny, "PNG")
    assert u.upload(sid, "left", tiny.getvalue()).json()["error"]["code"] == "image_too_small"


def test_png_is_accepted_and_stored_as_jpeg(alice):
    alice.consent()
    sid = alice.post(f"{API}/screenings", json=NO).json()["id"]
    buf = BytesIO()
    Image.fromarray(__import__("numpy").random.default_rng(3).integers(0, 255, (700, 700, 3), dtype="uint8")).save(buf, "PNG")
    r = alice.upload(sid, "left", buf.getvalue(), "foot.png", "image/png")
    assert r.status_code == 201
    assert Image.open(BytesIO(alice.get(r.json()["url"]).content)).format == "JPEG"


def test_gps_and_device_metadata_are_stripped(alice):
    raw = sharp_jpeg(exif=True)
    assert len(Image.open(BytesIO(raw)).getexif()) > 0  # the test image really has EXIF
    alice.consent()
    sid = alice.post(f"{API}/screenings", json=NO).json()["id"]
    r = alice.upload(sid, "left", raw)
    stored = Image.open(BytesIO(alice.get(r.json()["url"]).content))
    assert len(stored.getexif()) == 0 and b"SecretPhoneMaker" not in alice.get(r.json()["url"]).content


def test_retake_replaces_the_old_photo_and_removes_the_old_object(ctx, alice):
    alice.consent()
    sid = alice.post(f"{API}/screenings", json=NO).json()["id"]
    alice.upload(sid, "left", sharp_jpeg(seed=1))
    with ctx.session_factory() as db:
        from app.models import ScreeningImage
        old = db.query(ScreeningImage).one().storage_path
    alice.upload(sid, "left", sharp_jpeg(seed=5))
    with ctx.session_factory() as db:
        rows = db.query(ScreeningImage).all()
        assert len(rows) == 1 and rows[0].storage_path != old
    with pytest.raises(StorageError):
        ctx.storage.get(old)
    assert alice.delete(f"{API}/screenings/{sid}/images/left").status_code == 204
    assert alice.get(f"{API}/screenings/{sid}").json()["images"] == []


def test_deleting_a_screening_deletes_its_images(ctx, alice):
    rep = alice.screen()
    with ctx.session_factory() as db:
        from app.models import ScreeningImage
        paths = [i.storage_path for i in db.query(ScreeningImage).all()]
    assert alice.delete(f"{API}/screenings/{rep['id']}").status_code == 204
    for p in paths:
        with pytest.raises(StorageError):
            ctx.storage.get(p)


def test_older_reports_are_marked_historical(alice):
    first = alice.screen()
    second = alice.screen()
    old = alice.get(f"{API}/screenings/{first['id']}").json()
    assert old["is_latest"] is False and old["eligibility"]["reason_code"] == "historical_report"
    assert alice.get(f"{API}/screenings/{second['id']}").json()["is_latest"] is True


def test_analysis_is_idempotent_for_completed_screenings(alice):
    rep = alice.screen()
    again = alice.post(f"{API}/screenings/analyze", json={"screening_id": rep["id"]}).json()
    assert again["completed_at"] == rep["completed_at"]
    assert alice.upload(rep["id"], "left", sharp_jpeg()).status_code == 409


def test_analyze_endpoint_is_rate_limited(make_app):
    client, _ = make_app(rate_limit_enabled=True)
    u = User(client)
    import uuid
    codes = [u.post(f"{API}/screenings/analyze", json={"screening_id": str(uuid.uuid4())}).status_code for _ in range(16)]
    assert codes[:15] == [404] * 15 and codes[15] == 429


def test_health_profile_needs_consent_then_roundtrips_and_validates(alice):
    assert alice.get(f"{API}/me/health-profile").json()["diabetes_type"] is None
    r = alice.put(f"{API}/me/health-profile", json={"diabetes_type": "type2"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "consent_required"
    alice.consent("health_data_processing")
    body = {"diabetes_type": "type2", "diabetes_duration_years": 8, "prior_foot_ulcer": "no",
            "foot_surgery_or_amputation": "not_sure", "current_symptoms_note": None}
    assert alice.put(f"{API}/me/health-profile", json=body).json() == body
    assert alice.get(f"{API}/me").json()["has_health_profile"] is True
    assert alice.put(f"{API}/me/health-profile", json={"diabetes_type": "type9"}).status_code == 422
