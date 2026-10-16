import pytest

from app.storage.base import StorageError
from app.tests.conftest import API, User, add_to_cart, checkout, first_variant


def test_export_contains_only_my_data(alice, bob):
    alice.get(f"{API}/me")
    alice.patch(f"{API}/me", json={"full_name": "Alice A"})
    alice.consent("health_data_processing")
    alice.put(f"{API}/me/health-profile", json={"diabetes_type": "type2"})
    alice.screen(symptoms={"open_wound": "not_sure"})
    bob.screen()
    data = alice.get(f"{API}/me/data-export").json()
    assert data["profile"]["full_name"] == "Alice A" and data["health_profile"]["diabetes_type"] == "type2"
    assert len(data["screenings"]) == 1 and data["screenings"][0]["symptoms"]["open_wound"] == "not_sure"
    assert data["consents"] == {"health_data_processing": True, "image_screening": True}
    assert "Bob" not in str(data)
    assert all("storage_path" not in i for s in data["screenings"] for i in s["images"])  # no internal paths leak


def test_account_deletion_removes_health_data_and_images_but_keeps_order_records(client, ctx):
    u = User(client)
    u.get(f"{API}/me")
    u.patch(f"{API}/me", json={"full_name": "Deletable", "phone": "9876543210"})
    u.consent("health_data_processing")
    u.put(f"{API}/me/health-profile", json={"diabetes_type": "type1", "current_symptoms_note": "private"})
    u.screen()
    _, v = first_variant(u)
    add_to_cart(u, v["id"])
    oid = checkout(u, delivery_instructions="leave at the gate").json()["order"]["id"]
    from app.models import AuditLog, HealthProfile, Order, Profile, Screening, ScreeningImage
    with ctx.session_factory() as db:
        paths = [i.storage_path for i in db.query(ScreeningImage).all()]
    assert paths
    assert u.delete(f"{API}/me").status_code == 204
    with ctx.session_factory() as db:
        assert db.query(Screening).count() == 0 and db.query(ScreeningImage).count() == 0
        assert db.query(HealthProfile).count() == 0
        p = db.get(Profile, u.id)
        assert p.email is None and p.phone is None and p.full_name == "Deleted user" and p.deleted_at is not None
        o = db.get(Order, __import__("uuid").UUID(oid))
        assert o is not None and o.delivery_instructions is None  # order kept for legal retention, free text removed
        assert "account_deleted" in [a.action for a in db.query(AuditLog)]
    for pth in paths:
        with pytest.raises(StorageError):
            ctx.storage.get(pth)
    assert u.get(f"{API}/me").status_code == 403


def test_deleting_one_account_does_not_touch_another(alice, bob):
    bob.screen()
    alice.get(f"{API}/me")
    alice.delete(f"{API}/me")
    assert len(bob.get(f"{API}/screenings").json()) == 1
