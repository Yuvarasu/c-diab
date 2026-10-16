import json
import uuid

from app.payments.base import hmac_hex
from app.tests.conftest import API, User, add_to_cart, checkout, first_variant, promote


def eligible_user(client, **kw):
    u = User(client)
    u.screen(**kw)
    return u


def stock_of(ctx, variant_id):
    from app.models import ProductVariant
    with ctx.session_factory() as db:
        return db.get(ProductVariant, uuid.UUID(variant_id)).stock


# ---- the screening gate ----
def test_checkout_without_any_screening_is_blocked_by_the_server(alice):
    _, v = first_variant(alice)
    add_to_cart(alice, v["id"])
    r = checkout(alice)
    assert r.status_code == 403 and r.json()["error"]["details"]["reason_code"] == "screening_required"


def test_frontend_flags_cannot_bypass_the_gate(alice):
    _, v = first_variant(alice)
    add_to_cart(alice, v["id"])
    r = checkout(alice, eligible=True, screening_eligible=True, clinical_review_approved=True,
                 screening_id=str(uuid.uuid4()))
    assert r.status_code in (403, 409)
    assert alice.get(f"{API}/orders").json() == []


def test_inconclusive_and_deeper_wound_results_never_qualify(make_app):
    for forced in ("undetermined", "deep"):
        client, _ = make_app(demo_force_outcome=forced)
        u = eligible_user(client)
        _, v = first_variant(u)
        add_to_cart(u, v["id"])
        r = checkout(u)
        assert r.status_code == 403 and r.json()["error"]["details"]["reason_code"] == "outcome_not_eligible", forced


def test_urgent_symptoms_block_checkout(client):
    u = eligible_user(client, symptoms={"discharge": "yes"})
    _, v = first_variant(u)
    add_to_cart(u, v["id"])
    assert checkout(u).json()["error"]["details"]["reason_code"] == "urgent_warning"


def test_demo_result_does_not_unlock_when_demo_eligibility_is_off(make_app):
    client, _ = make_app(allow_demo_eligibility=False)
    u = eligible_user(client)
    _, v = first_variant(u)
    add_to_cart(u, v["id"])
    assert checkout(u).json()["error"]["details"]["reason_code"] == "demo_result_not_eligible"


def test_strict_policy_clinical_review_cannot_be_bypassed_and_unlocks_after_approval(make_app):
    client, ctx = make_app(policy_config_path="policy/policy.default.json")
    admin, doc, u = User(client), User(client), User(client)
    for x in (admin, doc, u):
        x.get(f"{API}/me")
    promote(ctx, admin.id, "admin")
    promote(ctx, doc.id, "clinical_reviewer")
    rep = u.screen()
    _, v = first_variant(u)
    add_to_cart(u, v["id"])
    assert checkout(u).json()["error"]["details"]["reason_code"] == "clinical_review_pending"
    assert rep["eligibility"]["clinical_review_pending"] is True
    assert admin.post(f"{API}/admin/screenings/{rep['id']}/assign", json={"reviewer_id": str(doc.id)}).status_code == 200
    assert doc.post(f"{API}/clinical/screenings/{rep['id']}/review",
                    json={"decision": "approved_for_footwear", "notes": "ok"}).status_code == 201
    assert u.get(f"{API}/screenings/eligibility").json()["eligible"] is True
    assert checkout(u).status_code == 201


def test_clinician_can_decline(make_app):
    client, ctx = make_app(policy_config_path="policy/policy.default.json")
    admin, doc, u = User(client), User(client), User(client)
    for x in (admin, doc, u):
        x.get(f"{API}/me")
    promote(ctx, admin.id, "admin")
    promote(ctx, doc.id, "clinical_reviewer")
    rep = u.screen()
    admin.post(f"{API}/admin/screenings/{rep['id']}/assign", json={"reviewer_id": str(doc.id)})
    doc.post(f"{API}/clinical/screenings/{rep['id']}/review", json={"decision": "needs_in_person_assessment"})
    _, v = first_variant(u)
    add_to_cart(u, v["id"])
    assert checkout(u).json()["error"]["details"]["reason_code"] == "clinical_review_declined"


def test_newer_screening_supersedes_older_good_one(client):
    u = eligible_user(client)
    old_id = u.get(f"{API}/screenings").json()[0]["id"]
    u.screen(symptoms={"discharge": "yes"})  # newer, urgent
    _, v = first_variant(u)
    add_to_cart(u, v["id"])
    r = checkout(u, screening_id=old_id)
    assert r.status_code == 409 and r.json()["error"]["code"] == "screening_superseded"
    assert checkout(u).status_code == 403


def test_products_that_do_not_require_screening_can_be_bought_without_one(client, ctx):
    admin, u = User(client), User(client)
    admin.get(f"{API}/me")
    promote(ctx, admin.id, "admin")
    p, v = first_variant(u)
    admin.patch(f"{API}/admin/products/{p['id']}", json={"requires_screening": False})
    add_to_cart(u, v["id"])
    assert checkout(u).status_code == 201


# ---- cart, pricing, stock ----
def test_cart_totals_and_shipping_rules(alice):
    p, v = first_variant(alice)
    cart = add_to_cart(alice, v["id"], 1)
    assert cart["subtotal_paise"] == p["price_paise"] and cart["shipping_paise"] == 9900
    assert cart["total_paise"] == cart["subtotal_paise"] + 9900 and cart["requires_screening"] is True
    cart = add_to_cart(alice, v["id"], 2)  # upsert quantity, not add
    assert cart["items"][0]["quantity"] == 2 and cart["shipping_paise"] == 9900 * 0  # 2 x 1499 >= free threshold
    r = alice.delete(f"{API}/cart/items/{v['id']}")
    assert r.json()["items"] == [] and r.json()["shipping_paise"] == 0


def test_cart_is_private_and_validates_stock(alice, bob):
    _, v = first_variant(alice)
    add_to_cart(alice, v["id"])
    assert bob.get(f"{API}/cart").json()["items"] == []
    r = alice.put(f"{API}/cart/items", json={"variant_id": v["id"], "quantity": 10})
    assert r.status_code == 200
    assert alice.put(f"{API}/cart/items", json={"variant_id": v["id"], "quantity": 11}).status_code == 422
    assert alice.put(f"{API}/cart/items", json={"variant_id": str(uuid.uuid4()), "quantity": 1}).status_code == 404


def test_cannot_put_more_than_stock_in_cart(ctx, alice):
    from app.models import ProductVariant
    _, v = first_variant(alice)
    with ctx.session_factory() as db:
        db.get(ProductVariant, uuid.UUID(v["id"])).stock = 2
        db.commit()
    r = alice.put(f"{API}/cart/items", json={"variant_id": v["id"], "quantity": 3})
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_stock"


def test_checkout_uses_database_prices_and_reserves_stock(client, ctx):
    u = eligible_user(client)
    p, v = first_variant(u)
    add_to_cart(u, v["id"], 2)
    before = stock_of(ctx, v["id"])
    r = checkout(u, unit_price_paise=1, total_paise=1, price_paise=1)  # tampering attempts are ignored
    assert r.status_code == 201
    o = r.json()["order"]
    assert o["subtotal_paise"] == 2 * p["price_paise"] and o["total_paise"] == o["subtotal_paise"] + o["shipping_paise"]
    assert o["status"] == "pending_payment" and o["items"][0]["unit_price_paise"] == p["price_paise"]
    assert r.json()["payment"]["provider"] == "mock" and r.json()["payment"]["amount_paise"] == o["total_paise"]
    assert stock_of(ctx, v["id"]) == before - 2


def test_stock_dropping_after_carting_blocks_checkout(client, ctx):
    from app.models import ProductVariant
    u = eligible_user(client)
    _, v = first_variant(u)
    add_to_cart(u, v["id"], 3)
    with ctx.session_factory() as db:
        db.get(ProductVariant, uuid.UUID(v["id"])).stock = 1
        db.commit()
    r = checkout(u)
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_stock"
    assert u.get(f"{API}/orders").json() == []


def test_empty_cart_cannot_check_out(client):
    assert checkout(eligible_user(client)).json()["error"]["code"] == "cart_empty"


def test_checkout_validates_the_shipping_form(client):
    u = eligible_user(client)
    _, v = first_variant(u)
    add_to_cart(u, v["id"])
    r = u.post(f"{API}/orders/checkout", json={"idempotency_key": "abcdefgh1", "shipping_name": "A", "shipping_phone": "12",
                                              "address_line1": "x", "city": "C", "state": "T", "pincode": "0"})
    assert r.status_code == 422


# ---- duplicate prevention ----
def test_duplicate_checkout_requests_create_one_order(client, ctx):
    u = eligible_user(client)
    _, v = first_variant(u)
    add_to_cart(u, v["id"])
    before = stock_of(ctx, v["id"])
    first, second = checkout(u, key="same-key-123"), checkout(u, key="same-key-123")
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["order"]["id"] == second.json()["order"]["id"]
    assert first.json()["payment"]["provider_order_id"] == second.json()["payment"]["provider_order_id"]
    assert len(u.get(f"{API}/orders").json()) == 1 and stock_of(ctx, v["id"]) == before - 1


# ---- payments ----
def pay(u, order_id, success=True):
    return u.post(f"{API}/payments/mock/complete", json={"order_id": order_id, "outcome": "success" if success else "failure"})


def place(client, ctx=None, qty=1):
    u = eligible_user(client)
    _, v = first_variant(u)
    add_to_cart(u, v["id"], qty)
    r = checkout(u).json()
    return u, v, r["order"]["id"], r["payment"]


def test_successful_payment_is_verified_server_side_and_clears_cart(client):
    u, v, oid, _ = place(client)
    auth = pay(u, oid).json()
    assert auth["status"] == "authorized"
    r = u.post(f"{API}/payments/verify", json={"order_id": oid, "provider_payment_id": auth["provider_payment_id"],
                                              "signature": auth["signature"]})
    assert r.status_code == 200 and r.json()["status"] == "paid" and r.json()["payment_status"] == "paid"
    assert u.get(f"{API}/cart").json()["items"] == []
    again = u.post(f"{API}/payments/verify", json={"order_id": oid, "provider_payment_id": auth["provider_payment_id"],
                                                  "signature": auth["signature"]})
    assert again.status_code == 200 and again.json()["status"] == "paid"  # idempotent, no double processing


def test_failed_payment_is_never_recorded_as_paid_and_stock_is_released(client, ctx):
    u, v, oid, _ = place(client, qty=2)
    reserved = stock_of(ctx, v["id"])
    assert pay(u, oid, success=False).json() == {"status": "failed"}
    o = u.get(f"{API}/orders/{oid}").json()
    assert o["status"] == "payment_failed" and o["payment_status"] == "failed"
    assert stock_of(ctx, v["id"]) == reserved + 2
    assert u.get(f"{API}/cart").json()["items"] != []  # cart kept so the user can retry
    r = u.post(f"{API}/payments/verify", json={"order_id": oid, "provider_payment_id": "pay_mock_whatever", "signature": "bad"})
    assert r.status_code == 409


def test_forged_or_replayed_signatures_are_rejected(client):
    u, _, oid, _ = place(client)
    r = u.post(f"{API}/payments/verify", json={"order_id": oid, "provider_payment_id": "pay_fake_1", "signature": "deadbeef"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_signature"
    assert u.get(f"{API}/orders/{oid}").json()["status"] == "pending_payment"
    # a genuine payment for order A cannot be replayed to confirm order B
    pa = pay(u, oid).json()
    _, v = first_variant(u)
    add_to_cart(u, v["id"])
    other = checkout(u).json()["order"]["id"]
    r = u.post(f"{API}/payments/verify", json={"order_id": other, "provider_payment_id": pa["provider_payment_id"],
                                              "signature": pa["signature"]})
    assert r.status_code == 400 and u.get(f"{API}/orders/{other}").json()["status"] == "pending_payment"


def test_other_users_cannot_pay_view_or_verify_my_order(client):
    u, _, oid, _ = place(client)
    mallory = User(client)
    assert mallory.get(f"{API}/orders/{oid}").status_code == 404
    assert pay(mallory, oid).status_code == 404
    auth = pay(u, oid).json()
    r = mallory.post(f"{API}/payments/verify", json={"order_id": oid, "provider_payment_id": auth["provider_payment_id"],
                                                    "signature": auth["signature"]})
    assert r.status_code == 404 and mallory.get(f"{API}/orders").json() == []


def webhook(client, ctx, event, order_id, payment_id, amount, sign=True):
    raw = json.dumps({"event": event, "payload": {"order_id": order_id, "payment_id": payment_id, "amount": amount}}).encode()
    sig = hmac_hex(ctx.payments.secret, raw) if sign else "bad"
    return client.post(f"{API}/payments/webhook", content=raw, headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"})


def test_webhook_requires_a_valid_signature(client, ctx):
    u, _, oid, pay_session = place(client)
    assert webhook(client, ctx, "payment.captured", pay_session["provider_order_id"], "pay_x", pay_session["amount_paise"], sign=False).status_code == 401
    assert u.get(f"{API}/orders/{oid}").json()["status"] == "pending_payment"


def test_signed_webhook_confirms_payment_once_and_checks_the_amount(client, ctx):
    u, _, oid, s = place(client)
    assert webhook(client, ctx, "payment.captured", s["provider_order_id"], "pay_w1", s["amount_paise"] + 1).status_code == 200
    assert u.get(f"{API}/orders/{oid}").json()["status"] == "pending_payment"  # wrong amount ignored
    assert webhook(client, ctx, "payment.captured", s["provider_order_id"], "pay_w1", s["amount_paise"]).status_code == 200
    assert u.get(f"{API}/orders/{oid}").json()["status"] == "paid"
    assert webhook(client, ctx, "payment.captured", s["provider_order_id"], "pay_w1", s["amount_paise"]).status_code == 200  # duplicate delivery
    assert webhook(client, ctx, "payment.failed", s["provider_order_id"], "pay_w2", s["amount_paise"]).status_code == 200
    assert u.get(f"{API}/orders/{oid}").json()["status"] == "paid"  # a late failure cannot un-pay it


def test_failed_webhook_marks_payment_failed_and_releases_stock(client, ctx):
    u, v, oid, s = place(client)
    reserved = stock_of(ctx, v["id"])
    webhook(client, ctx, "payment.failed", s["provider_order_id"], "pay_f1", s["amount_paise"])
    assert u.get(f"{API}/orders/{oid}").json()["status"] == "payment_failed"
    assert stock_of(ctx, v["id"]) == reserved + 1


def test_mock_payments_are_unavailable_outside_the_mock_provider(ctx, client):
    ctx.payments.name = "razorpay"  # simulate a real provider being active
    u = User(client)
    assert pay(u, str(uuid.uuid4())).status_code == 404
