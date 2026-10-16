import os
import time
import uuid
from io import BytesIO

import jwt
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from app.core.config import Settings
from app.main import create_app
from app.models import Profile
from app.seed import seed_products

SECRET = "test-secret-" + "x" * 40
PG_URL = os.environ.get("TEST_DATABASE_URL")  # set by scripts/pg_verify.py to run the suite on the real SQL migrations
TABLES = ("audit_logs, payments, order_items, orders, cart_items, product_variants, products, clinical_reviews, "
          "screening_images, screenings, consent_records, health_profiles, profiles")
API = "/api/v1"
NO = dict(open_wound="no", redness_swelling="no", unusually_warm="no", discharge="no",
          skin_color_change="no", new_or_worsening_wound="no")


def token(uid, *, exp_in=3600, secret=SECRET, aud="authenticated", alg="HS256", **extra):
    claims = {"sub": str(uid), "aud": aud, "exp": int(time.time()) + exp_in, **extra}
    return jwt.encode(claims, secret, algorithm=alg)


def sharp_jpeg(size=(800, 800), seed=0, exif=False) -> bytes:
    arr = np.random.default_rng(seed).integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
    img, buf = Image.fromarray(arr), BytesIO()
    if exif:
        e = Image.Exif()
        e[0x010F] = "SecretPhoneMaker"  # Make
        e[0x8825] = {1: "N", 2: (13.0, 4.0, 0.0)}  # GPS IFD
        img.save(buf, "JPEG", quality=92, exif=e)
    else:
        img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def flat_jpeg(value=128, size=(800, 800)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (value,) * 3).save(buf, "JPEG")
    return buf.getvalue()


def dark_jpeg() -> bytes:
    arr = np.random.default_rng(1).integers(0, 20, (800, 800, 3), dtype=np.uint8)
    buf = BytesIO()
    Image.fromarray(arr).save(buf, "JPEG")
    return buf.getvalue()


class User:
    def __init__(self, client: TestClient, uid=None):
        self.client, self.id = client, uid or uuid.uuid4()

    @property
    def headers(self):
        return {"Authorization": f"Bearer {token(self.id)}"}

    def get(self, url, **kw):
        return self.client.get(url, headers=self.headers, **kw)

    def post(self, url, **kw):
        return self.client.post(url, headers=self.headers, **kw)

    def put(self, url, **kw):
        return self.client.put(url, headers=self.headers, **kw)

    def patch(self, url, **kw):
        return self.client.patch(url, headers=self.headers, **kw)

    def delete(self, url, **kw):
        return self.client.delete(url, headers=self.headers, **kw)

    def upload(self, sid, side, data, name="foot.jpg", ctype="image/jpeg"):
        return self.client.post(f"{API}/screenings/{sid}/images", headers=self.headers,
                                data={"side": side}, files={"file": (name, data, ctype)})

    def consent(self, *types):
        for t in types or ("health_data_processing", "image_screening"):
            assert self.post(f"{API}/me/consents", json={"consent_type": t, "granted": True}).status_code == 200

    def screen(self, symptoms=None, left=None, right=None, analyze=True, consent=True):
        """Runs the whole screening flow and returns the final report JSON."""
        if consent:
            self.consent()
        r = self.post(f"{API}/screenings", json={**NO, **(symptoms or {})})
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        for side, data in (("left", left or sharp_jpeg(seed=1)), ("right", right or sharp_jpeg(seed=2))):
            assert self.upload(sid, side, data).status_code == 201
        if not analyze:
            return r.json()
        r = self.post(f"{API}/screenings/analyze", json={"screening_id": sid})
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture
def make_app(tmp_path):
    def _make(**overrides):
        base = dict(app_env="test", database_url="sqlite://", supabase_jwt_secret=SECRET,
                    local_storage_dir=str(tmp_path / "store"), policy_config_path="policy/policy.demo.json",
                    allow_demo_eligibility=True, demo_force_outcome="none", rate_limit_enabled=False)
        if PG_URL and "database_url" not in overrides:
            base["database_url"] = PG_URL
        base.update(overrides)
        app = create_app(Settings(**base))
        ctx = app.state.ctx
        if PG_URL and base["database_url"] == PG_URL:
            with ctx.engine.begin() as c:
                c.execute(text(f"truncate table {TABLES} restart identity cascade"))
        with ctx.session_factory() as db:
            seed_products(db)
        return TestClient(app), ctx
    return _make


@pytest.fixture
def env(make_app):
    client, ctx = make_app()
    return client, ctx


@pytest.fixture
def client(env):
    return env[0]


@pytest.fixture
def ctx(env):
    return env[1]


@pytest.fixture
def alice(client):
    return User(client)


@pytest.fixture
def bob(client):
    return User(client)


def promote(ctx, uid, role):
    with ctx.session_factory() as db:
        p = db.get(Profile, uid)
        if p is None:
            db.add(Profile(id=uid, role=role))
        else:
            p.role = role
        db.commit()


def first_variant(user, in_stock_min=1):
    products = user.get(f"{API}/products").json()
    p = products[0]
    v = next(v for v in p["variants"] if v["max_quantity"] >= in_stock_min)
    return p, v


ADDRESS = dict(shipping_name="Test User", shipping_phone="9876543210", address_line1="12 Test Street",
               city="Chennai", state="Tamil Nadu", pincode="600001")


def checkout(user, key=None, **extra):
    return user.post(f"{API}/orders/checkout", json={**ADDRESS, "idempotency_key": key or uuid.uuid4().hex, **extra})


def add_to_cart(user, variant_id, qty=1):
    r = user.put(f"{API}/cart/items", json={"variant_id": variant_id, "quantity": qty})
    assert r.status_code == 200, r.text
    return r.json()
