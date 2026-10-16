import uuid

import pytest

from app.models import AuditLog
from app.tests.conftest import API, User, add_to_cart, checkout, first_variant, promote


@pytest.fixture
def roles(client, ctx):
    admin, doc, doc2, cust = User(client), User(client), User(client), User(client)
    for u in (admin, doc, doc2, cust):
        u.get(f"{API}/me")
    promote(ctx, admin.id, "admin")
    promote(ctx, doc.id, "clinical_reviewer")
    promote(ctx, doc2.id, "clinical_reviewer")
    return admin, doc, doc2, cust


def actions(ctx):
    with ctx.session_factory() as db:
        return [a.action for a in db.query(AuditLog).order_by(AuditLog.created_at)]


ADMIN_GETS = ["/admin/products", "/admin/orders", "/admin/analytics", "/admin/review-queue", "/admin/reviewers"]
CLINICAL_GETS = ["/clinical/queue"]


@pytest.mark.parametrize("path", ADMIN_GETS)
def test_admin_endpoints_reject_customers_and_clinicians(roles, path):
    admin, doc, _, cust = roles
    assert cust.get(f"{API}{path}").status_code == 403
    assert doc.get(f"{API}{path}").status_code == 403
    assert admin.get(f"{API}{path}").status_code == 200


@pytest.mark.parametrize("path", CLINICAL_GETS)
def test_clinical_endpoints_reject_admins_and_customers(roles, path):
    admin, doc, _, cust = roles
    assert admin.get(f"{API}{path}").status_code == 403
    assert cust.get(f"{API}{path}").status_code == 403
    assert doc.get(f"{API}{path}").status_code == 200


def test_product_management_with_audit_trail(roles, ctx):
    admin, _, _, cust = roles
    body = {"slug": "new-slipper", "name": "New Slipper", "price_paise": 129900,
            "variants": [{"size": "UK 7", "stock": 4}, {"size": "UK 8", "stock": 0}]}
    assert cust.post(f"{API}/admin/products", json=body).status_code == 403
    p = admin.post(f"{API}/admin/products", json=body).json()
    assert admin.post(f"{API}/admin/products", json=body).status_code == 409  # duplicate slug
    assert [v["stock"] for v in p["variants"]] == [4, 0]
    # shoppers see stock status, not raw counts
    shop = {x["slug"]: x for x in cust.get(f"{API}/products").json()}["new-slipper"]
    assert {v["size"]: v["stock_status"] for v in shop["variants"]} == {"UK 7": "low_stock", "UK 8": "out_of_stock"}
    assert "stock" not in shop["variants"][0]
    admin.patch(f"{API}/admin/products/{p['id']}", json={"price_paise": 139900, "active": False})
    assert "new-slipper" not in {x["slug"] for x in cust.get(f"{API}/products").json()}  # inactive products are hidden
    assert cust.get(f"{API}/products/{p['id']}").status_code == 404
    vid = p["variants"][0]["id"]
    out = admin.patch(f"{API}/admin/variants/{vid}", json={"stock": 50}).json()
    assert {v["id"]: v["stock"] for v in out["variants"]}[vid] == 50
    assert admin.patch(f"{API}/admin/variants/{vid}", json={"stock": -1}).status_code == 422
    assert {"product_created", "product_updated", "variant_updated"} <= set(actions(ctx))


def test_order_status_workflow_and_cancellation_restocks(roles, client, ctx):
    admin, _, _, _ = roles
    u = User(client)
    u.screen()
    _, v = first_variant(u)
    add_to_cart(u, v["id"], 2)
    oid = checkout(u).json()["order"]["id"]
    pay = u.post(f"{API}/payments/mock/complete", json={"order_id": oid, "outcome": "success"}).json()
    u.post(f"{API}/payments/verify", json={"order_id": oid, "provider_payment_id": pay["provider_payment_id"], "signature": pay["signature"]})
    assert admin.put(f"{API}/admin/orders/{oid}/status", json={"status": "delivered"}).status_code == 409  # cannot skip steps
    assert admin.put(f"{API}/admin/orders/{oid}/status", json={"status": "processing"}).json()["status"] == "processing"
    assert admin.put(f"{API}/admin/orders/{oid}/status", json={"status": "shipped"}).json()["status"] == "shipped"
    assert admin.put(f"{API}/admin/orders/{oid}/status", json={"status": "cancelled"}).status_code == 409  # shipped can't cancel
    assert u.get(f"{API}/orders/{oid}").json()["status"] == "shipped"
    assert admin.put(f"{API}/admin/orders/{oid}/status", json={"status": "delivered"}).json()["status"] == "delivered"
    assert admin.get(f"{API}/admin/orders?status=delivered").json()[0]["id"] == oid
    assert u.put(f"{API}/admin/orders/{oid}/status", json={"status": "cancelled"}).status_code == 403
    assert actions(ctx).count("order_status_changed") == 3

    # cancelling an unfinished order returns stock
    from app.models import ProductVariant
    with ctx.session_factory() as db:
        before = db.get(ProductVariant, uuid.UUID(v["id"])).stock
    add_to_cart(u, v["id"], 1)
    oid2 = checkout(u).json()["order"]["id"]
    assert admin.put(f"{API}/admin/orders/{oid2}/status", json={"status": "cancelled"}).status_code == 200
    with ctx.session_factory() as db:
        assert db.get(ProductVariant, uuid.UUID(v["id"])).stock == before


def test_analytics_has_no_health_detail(roles):
    admin, _, _, _ = roles
    a = admin.get(f"{API}/admin/analytics").json()
    assert set(a) == {"orders_by_status", "revenue_paise", "low_stock", "screenings_total"}


def test_admins_can_route_cases_but_never_see_photos_symptoms_or_identities(roles, client):
    admin, doc, _, _ = roles
    u = User(client)
    u.get(f"{API}/me")
    rep = u.screen(symptoms={"open_wound": "not_sure"})  # clinical_review_required
    q = admin.get(f"{API}/admin/review-queue").json()
    assert [r["screening_id"] for r in q] == [rep["id"]]
    assert set(q[0]) == {"screening_id", "created_at", "outcome", "assigned_reviewer_id", "reviewed"}
    # admins have no way to fetch the report or images of any user
    assert admin.get(f"{API}/screenings/{rep['id']}").status_code == 404
    assert admin.get(rep["images"][0]["url"]).status_code == 404
    assert admin.get(f"{API}/clinical/screenings/{rep['id']}").status_code == 403
    assert admin.get(f"{API}/clinical/screenings/{rep['id']}/images/{rep['images'][0]['id']}/content").status_code == 403
    assert {r["id"] for r in admin.get(f"{API}/admin/reviewers").json()} == {str(doc.id), str(roles[2].id)}


def test_assignment_validation(roles, client):
    admin, doc, _, cust = roles
    u = User(client)
    rep = u.screen(symptoms={"open_wound": "not_sure"})
    assert admin.post(f"{API}/admin/screenings/{rep['id']}/assign", json={"reviewer_id": str(cust.id)}).status_code == 422
    assert admin.post(f"{API}/admin/screenings/{uuid.uuid4()}/assign", json={"reviewer_id": str(doc.id)}).status_code == 404
    ok = u.screen()  # routine, no review needed under the demo policy: not in the clinician queue
    assert admin.post(f"{API}/admin/screenings/{ok['id']}/assign", json={"reviewer_id": str(doc.id)}).status_code == 404
    assert cust.post(f"{API}/admin/screenings/{rep['id']}/assign", json={"reviewer_id": str(doc.id)}).status_code == 403


def test_reviewers_only_see_cases_assigned_to_them_and_every_view_is_audited(roles, client, ctx):
    admin, doc, doc2, _ = roles
    u = User(client)
    rep = u.screen(symptoms={"open_wound": "not_sure"})
    sid, img = rep["id"], rep["images"][0]
    assert doc.get(f"{API}/clinical/queue").json() == []
    assert doc.get(f"{API}/clinical/screenings/{sid}").status_code == 404  # not assigned yet
    admin.post(f"{API}/admin/screenings/{sid}/assign", json={"reviewer_id": str(doc.id)})
    q = doc.get(f"{API}/clinical/queue").json()
    assert len(q) == 1 and q[0]["reference"] == sid[:8] and "email" not in q[0] and "user_id" not in q[0]
    d = doc.get(f"{API}/clinical/screenings/{sid}").json()
    assert d["symptoms"]["open_wound"] == "not_sure" and len(d["images"]) == 2
    assert doc.get(d["images"][0]["url"]).status_code == 200
    # a different clinician cannot see it
    assert doc2.get(f"{API}/clinical/screenings/{sid}").status_code == 404
    assert doc2.get(f"{API}/clinical/screenings/{sid}/images/{img['id']}/content").status_code == 404
    assert doc2.post(f"{API}/clinical/screenings/{sid}/review", json={"decision": "approved_for_footwear"}).status_code == 404
    # the clinician route does not work for the patient's own endpoints either
    assert doc.get(f"{API}/screenings/{sid}").status_code == 404
    log = actions(ctx)
    assert {"review_assigned", "clinical_record_viewed", "clinical_image_viewed"} <= set(log)


def test_reviews_can_only_be_filed_for_completed_screenings(roles, client):
    admin, doc, _, _ = roles
    u = User(client)
    draft = u.screen(analyze=False)  # draft, never completed
    from app.tests.conftest import promote  # noqa: F401
    assert doc.post(f"{API}/clinical/screenings/{draft['id']}/review", json={"decision": "not_suitable"}).status_code == 404
