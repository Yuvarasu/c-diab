import uuid

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.tests.conftest import API, SECRET, User, promote, token


def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ai_backend"] == "demo"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nonsense"}, {"Authorization": "Basic abc"}])
def test_missing_or_garbage_token_is_401(client, headers):
    assert client.get(f"{API}/me", headers=headers).status_code == 401


def bad_tokens():
    uid = uuid.uuid4()
    return {
        "expired": token(uid, exp_in=-3600),
        "wrong_secret": token(uid, secret="y" * 48),
        "wrong_audience": token(uid, aud="anon"),
        "not_a_uuid": token("not-a-uuid"),
        "alg_none": jwt.encode({"sub": str(uid), "aud": "authenticated", "exp": 9999999999}, None, algorithm="none"),
    }


@pytest.mark.parametrize("name", list(bad_tokens()))
def test_invalid_tokens_rejected(client, name):
    r = client.get(f"{API}/me", headers={"Authorization": f"Bearer {bad_tokens()[name]}"})
    assert r.status_code == 401, name


def test_hs256_token_rejected_when_no_secret_is_configured(make_app):
    client, _ = make_app(supabase_jwt_secret="")
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {token(uuid.uuid4())}"}).status_code == 401


def test_role_claims_in_the_token_never_grant_admin(client):
    uid = uuid.uuid4()
    t = token(uid, app_metadata={"role": "admin"}, user_metadata={"role": "admin"}, role="admin")
    r = client.get(f"{API}/admin/products", headers={"Authorization": f"Bearer {t}"})
    assert r.status_code == 403


def test_profile_is_created_on_first_authenticated_request(client, alice):
    r = alice.get(f"{API}/me")
    assert r.status_code == 200 and r.json()["role"] == "customer" and r.json()["id"] == str(alice.id)


def test_users_cannot_change_their_own_role(client, alice):
    r = alice.patch(f"{API}/me", json={"role": "admin", "full_name": "Alice"})
    assert r.status_code == 200 and r.json()["role"] == "customer" and r.json()["full_name"] == "Alice"
    assert alice.get(f"{API}/admin/products").status_code == 403


def test_validation_errors_do_not_echo_submitted_values(alice):
    r = alice.put(f"{API}/me/health-profile", json={"diabetes_duration_years": 999, "current_symptoms_note": "secret-note"})
    assert r.status_code == 422 and "secret-note" not in r.text and "999" not in r.text


def test_deleted_accounts_are_locked_out(client, ctx, alice):
    alice.get(f"{API}/me")
    assert alice.delete(f"{API}/me").status_code == 204
    assert alice.get(f"{API}/me").status_code == 403


# ---- production configuration guards ----
PROD_OK = dict(app_env="production", ai_backend="http", model_service_url="https://model.example/analyze",
               storage_backend="supabase", supabase_url="https://x.supabase.co", supabase_service_role_key="k",
               payment_provider="razorpay", razorpay_key_id="rzp_live_x", razorpay_key_secret="s",
               razorpay_webhook_secret="w", database_url="postgresql://u:p@db.example:5432/postgres")


def test_valid_production_config_is_accepted():
    assert Settings(**PROD_OK).is_production


@pytest.mark.parametrize("change", [dict(ai_backend="demo"), dict(demo_force_outcome="none"), dict(allow_demo_eligibility=True),
                                    dict(payment_provider="mock"), dict(storage_backend="local"),
                                    dict(database_url="sqlite:///x.db"), dict(supabase_url=""), dict(razorpay_webhook_secret="")])
def test_production_refuses_unsafe_settings(change):
    with pytest.raises(ValidationError):
        Settings(**{**PROD_OK, **change})


def test_production_default_settings_fail_closed():
    with pytest.raises(ValidationError):
        Settings(app_env="production")
