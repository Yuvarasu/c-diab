"""End-to-end smoke test against a RUNNING server over real HTTP.

    python scripts/e2e_smoke.py http://127.0.0.1:8000

Mints a throw-away user token with the same SUPABASE_JWT_SECRET the server uses (set it in the environment).
Walks the whole journey: gate -> consent -> screening -> photos -> analysis -> eligibility -> order -> payment.
"""
import os
import sys
import time
import uuid
from io import BytesIO

import httpx
import jwt
import numpy as np
from PIL import Image

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
SECRET = os.environ["SUPABASE_JWT_SECRET"]
API = f"{BASE}/api/v1"
uid = uuid.uuid4()
H = {"Authorization": "Bearer " + jwt.encode({"sub": str(uid), "aud": "authenticated", "exp": int(time.time()) + 3600}, SECRET, algorithm="HS256")}
step = 0


def ok(msg):
    global step
    step += 1
    print(f"  {step:>2}. PASS  {msg}")


def photo(seed):
    buf = BytesIO()
    Image.fromarray(np.random.default_rng(seed).integers(0, 256, (800, 800, 3), dtype=np.uint8)).save(buf, "JPEG", quality=92)
    return buf.getvalue()


with httpx.Client(headers=H, timeout=30) as c:
    h = httpx.get(f"{BASE}/health").json()
    assert h["status"] == "ok"
    ok(f"server up (env={h['env']}, ai={h['ai_backend']}, payments={h['payment_provider']}, policy approved={h['policy_clinically_approved']})")
    assert httpx.get(f"{API}/me").status_code == 401
    ok("API refuses requests without a login token")

    products = c.get(f"{API}/products").json()
    variant = next(v for v in products[0]["variants"] if v["max_quantity"] > 0)
    assert c.put(f"{API}/cart/items", json={"variant_id": variant["id"], "quantity": 1}).status_code == 200
    ok(f"browsed {len(products)} products and added one to the cart")

    addr = dict(shipping_name="Demo User", shipping_phone="9876543210", address_line1="12 Test Street", city="Chennai", state="Tamil Nadu", pincode="600001")
    r = c.post(f"{API}/orders/checkout", json={**addr, "idempotency_key": uuid.uuid4().hex})
    assert r.status_code == 403 and r.json()["error"]["details"]["reason_code"] == "screening_required"
    ok("checkout is BLOCKED by the server before any screening (screening_required)")

    r = c.post(f"{API}/screenings", json=dict(open_wound="no", redness_swelling="no", unusually_warm="no", discharge="no", skin_color_change="no", new_or_worsening_wound="no"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "consent_required"
    ok("screening is blocked until consent is given")
    for t in ("health_data_processing", "image_screening"):
        assert c.post(f"{API}/me/consents", json={"consent_type": t, "granted": True}).status_code == 200

    s = c.post(f"{API}/screenings", json=dict(open_wound="no", redness_swelling="no", unusually_warm="no", discharge="no", skin_color_change="no", new_or_worsening_wound="no")).json()
    assert s["triage_level"] == "routine"
    for side, seed in (("left", 1), ("right", 2)):
        r = c.post(f"{API}/screenings/{s['id']}/images", data={"side": side}, files={"file": (f"{side}.jpg", photo(seed), "image/jpeg")})
        assert r.status_code == 201 and r.json()["quality_ok"], r.text
    ok("answered the questionnaire and uploaded both photos (validated, EXIF stripped, quality-checked)")

    rep = c.post(f"{API}/screenings/analyze", json={"screening_id": s["id"]}).json()
    assert rep["status"] == "completed" and rep["is_demo"] and rep["demo_banner"] == "DEMO RESULT — NOT A MEDICAL ASSESSMENT"
    ok(f"analysis finished: outcome={rep['outcome']!r}, labelled '{rep['demo_banner']}'")
    img = c.get(BASE + rep["images"][0]["url"])
    assert img.status_code == 200 and httpx.get(BASE + rep["images"][0]["url"]).status_code == 401
    ok("photo is served only with the owner's token (401 without it)")

    el = c.get(f"{API}/screenings/eligibility").json()
    assert el["eligible"] and el["is_demo"]
    ok(f"server-side eligibility: eligible={el['eligible']} ({el['message']})")

    co = c.post(f"{API}/orders/checkout", json={**addr, "idempotency_key": "e2e-" + uuid.uuid4().hex}).json()
    oid = co["order"]["id"]
    assert co["order"]["status"] == "pending_payment"
    ok(f"order created from DATABASE prices: total={co['order']['total_paise'] / 100:.2f} INR, status=pending_payment")

    pay = c.post(f"{API}/payments/mock/complete", json={"order_id": oid, "outcome": "success"}).json()
    bad = c.post(f"{API}/payments/verify", json={"order_id": oid, "provider_payment_id": pay["provider_payment_id"], "signature": "forged-signature"})
    assert bad.status_code == 400 and c.get(f"{API}/orders/{oid}").json()["status"] == "pending_payment"
    ok("forged payment signature rejected; order still unpaid")
    good = c.post(f"{API}/payments/verify", json={"order_id": oid, "provider_payment_id": pay["provider_payment_id"], "signature": pay["signature"]}).json()
    assert good["status"] == "paid" and good["payment_status"] == "paid"
    ok("genuine signed payment verified on the server; order is paid")
    assert c.get(f"{API}/cart").json()["items"] == []
    ok("cart cleared after payment")

    export = c.get(f"{API}/me/data-export").json()
    assert len(export["screenings"]) == 1 and len(export["orders"]) == 1
    ok("data export returns the user's screening and order")

print(f"\nEnd-to-end journey passed ({step} checks) against {BASE}")
