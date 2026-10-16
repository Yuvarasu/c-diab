"""Applies the SQL migrations to a throwaway PostgreSQL, verifies RLS / storage / constraints, then runs the whole
backend test-suite against that SQL schema (so the models and the migrations cannot drift apart).

    pip install pgserver psycopg[binary]
    python scripts/pg_verify.py
"""
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pgserver
import psycopg
from psycopg import errors as pe

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "database"
passed: list[str] = []


def ok(name: str) -> None:
    passed.append(name)
    print(f"  PASS  {name}")


def run(conn, sql, *, uid=None, role="authenticated", params=None):
    """Runs SQL as a Supabase-style role with request.jwt.claim.sub set, inside a rolled-back transaction."""
    with conn.transaction(force_rollback=True):
        conn.execute(f"set local role {role}")
        if uid:
            conn.execute("select set_config('request.jwt.claim.sub', %s, true)", (str(uid),))
        cur = conn.execute(sql, params)
        return cur.fetchall() if cur.description else cur.rowcount


def denied(conn, sql, **kw) -> bool:
    try:
        run(conn, sql, **kw)
    except (pe.InsufficientPrivilege, pe.CheckViolation, pe.UniqueViolation, pe.NotNullViolation):
        return True
    return False


def checks(conn) -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    conn.execute("insert into auth.users (id, email, raw_user_meta_data) values (%s,'a@x.test','{\"full_name\":\"Alice\",\"role\":\"admin\"}'), (%s,'b@x.test','{}')", (a, b))
    row = conn.execute("select full_name, role from public.profiles where id=%s", (a,)).fetchone()
    assert row == ("Alice", "customer"), row  # trigger created the profile; user-editable metadata cannot set the role
    ok("sign-up trigger creates a customer profile and ignores role in user metadata")

    sa, sb = uuid.uuid4(), uuid.uuid4()
    for sid, uid in ((sa, a), (sb, b)):
        conn.execute("insert into screenings (id,user_id,status,triage_level,policy_version) values (%s,%s,'draft','routine','t')", (sid, uid))
        conn.execute("insert into screening_images (screening_id,user_id,side,storage_path,size_bytes,width,height) values (%s,%s,'left','p',1,1,1)", (sid, uid))
        conn.execute("insert into health_profiles (user_id, diabetes_type) values (%s,'type2')", (uid,))
        conn.execute("insert into consent_records (user_id,consent_type,granted,policy_version) values (%s,'terms',true,'v')", (uid,))
    conn.execute("insert into clinical_reviews (screening_id,reviewer_id,decision) values (%s,%s,'not_suitable')", (sa, b))
    pid = conn.execute("select id from products where slug='cdiab-comfort-step'").fetchone()[0]
    vid = conn.execute("select id from product_variants where product_id=%s limit 1", (pid,)).fetchone()[0]
    orders = {}
    for uid in (a, b):
        oid = uuid.uuid4()
        orders[uid] = oid
        conn.execute("insert into orders (id,user_id,subtotal_paise,shipping_paise,total_paise,shipping_name,shipping_phone,idempotency_key) values (%s,%s,1,0,1,'n','p',%s)", (oid, uid, "key-" + str(uid)))
        conn.execute("insert into order_items (order_id,variant_id,product_name,size,unit_price_paise,quantity) values (%s,%s,'x','UK 6',1,1)", (oid, vid))
        conn.execute("insert into payments (order_id,provider,provider_order_id,amount_paise) values (%s,'mock','o_1',1)", (oid,))
        conn.execute("insert into cart_items (user_id,variant_id,quantity) values (%s,%s,1)", (uid, vid))
    conn.execute("insert into audit_logs (action, entity_type) values ('x','y')")

    for table, col in (("profiles", "id"), ("health_profiles", "user_id"), ("consent_records", "user_id"), ("screenings", "user_id"),
                       ("screening_images", "user_id"), ("cart_items", "user_id"), ("orders", "user_id")):
        mine = run(conn, f"select {col} from {table}", uid=a)
        assert mine and all(r[0] == a for r in mine), (table, mine)
        assert run(conn, f"select 1 from {table} where {col} = %s", uid=a, params=(b,)) == [], table
    ok("a user sees only their own profile, health profile, consents, screenings, image rows, cart and orders")

    for table in ("order_items", "payments"):
        assert len(run(conn, f"select 1 from {table}", uid=a)) == 1, table
    assert [r[0] for r in run(conn, "select decision from clinical_reviews", uid=a)] == ["not_suitable"]
    assert run(conn, "select 1 from clinical_reviews", uid=b) == []  # the reviewer is not the patient: no visibility via RLS
    assert run(conn, "select 1 from clinical_reviews", uid=uuid.uuid4()) == []
    ok("order items, payments and clinical reviews are visible only through the owning order/screening")

    assert run(conn, "select 1 from screenings", uid=None) == [], "no uid => no rows"
    ok("an authenticated session without a user id sees nothing")

    assert denied(conn, "select * from audit_logs", uid=a)
    assert denied(conn, "select * from public.profiles", role="anon")
    assert denied(conn, "select * from public.products", role="anon")
    ok("audit logs are unreadable to clients and anon has no table access at all")

    for sql in ("update profiles set role='admin' where id = auth.uid()",
                "insert into profiles (id, role) values (gen_random_uuid(), 'admin')",
                "update screenings set outcome='no_obvious_wound'",
                "delete from screenings",
                "insert into orders (user_id,subtotal_paise,shipping_paise,total_paise,shipping_name,shipping_phone,idempotency_key) values (auth.uid(),1,0,1,'n','p','k')",
                "update orders set status='paid'",
                "update payments set status='paid'",
                "insert into clinical_reviews (screening_id,reviewer_id,decision) select id, auth.uid(), 'approved_for_footwear' from screenings",
                "update product_variants set stock = 9999", "update products set price_paise = 1",
                "insert into consent_records (user_id,consent_type,granted,policy_version) values (auth.uid(),'terms',true,'v')"):
        assert denied(conn, sql, uid=a), sql
    ok("clients cannot escalate roles or write profiles, screenings, orders, payments, reviews, stock, prices or consents directly")

    conn.execute("insert into products (slug,name,price_paise,active) values ('hidden','Hidden',100,false)")
    hid = conn.execute("select id from products where slug='hidden'").fetchone()[0]
    conn.execute("insert into product_variants (product_id,size,stock) values (%s,'UK 7',5)", (hid,))
    slugs = {r[0] for r in run(conn, "select slug from products", uid=a)}
    assert "hidden" not in slugs and "cdiab-comfort-step" in slugs
    assert all(r[0] != hid for r in run(conn, "select product_id from product_variants", uid=a))
    ok("inactive products and their variants are hidden from shoppers")

    conn.execute("insert into storage.buckets (id,name) values ('other','other') on conflict do nothing")
    conn.execute("insert into storage.objects (bucket_id, name) values ('screening-images', %s), ('screening-images', %s), ('other', %s)",
                 (f"{a}/{sa}/left-1.jpg", f"{b}/{sb}/left-2.jpg", f"{a}/x.jpg"))
    names = [r[0] for r in run(conn, "select name from storage.objects", uid=a)]
    assert names == [f"{a}/{sa}/left-1.jpg"], names
    assert denied(conn, "insert into storage.objects (bucket_id, name) values ('screening-images', %s)", uid=a, params=(f"{a}/{sa}/evil.jpg",))
    assert denied(conn, "insert into storage.objects (bucket_id, name) values ('screening-images', %s)", uid=a, params=(f"{b}/{sb}/evil.jpg",))
    assert run(conn, "delete from storage.objects", uid=a) == 0
    bucket = conn.execute("select public, file_size_limit, allowed_mime_types from storage.buckets where id='screening-images'").fetchone()
    assert bucket == (False, 8388608, ["image/jpeg"]), bucket
    ok("storage: bucket is private, JPEG-only, 8 MB; a user can read only their own folder and cannot write or delete")

    assert run(conn, "select count(*) from screenings", role="service_role")[0][0] == 2
    ok("the service role (backend) bypasses RLS")

    bad = {
        "negative stock": "update product_variants set stock = -1",
        "unknown role": "insert into profiles (id, role) values (gen_random_uuid(), 'superuser')",
        "unknown outcome": "update screenings set outcome='definitely_fine'",
        "confidence > 1": "update screenings set confidence = 1.5",
        "negative price": "update products set price_paise = -5",
        "unknown order status": "update orders set status='teleported'",
        "zero quantity": "update cart_items set quantity = 0",
    }
    for name, sql in bad.items():
        assert denied(conn, sql, role="service_role"), name
    conn.execute("insert into payments (order_id,provider,provider_order_id,provider_payment_id,amount_paise) values (%s,'mock','o_2','pay_1',1)", (orders[a],))
    assert denied(conn, "insert into payments (order_id,provider,provider_order_id,provider_payment_id,amount_paise) values (%s,'mock','o_3','pay_1',1)",
                  role="service_role", params=(orders[b],))
    assert denied(conn, "insert into orders (user_id,subtotal_paise,shipping_paise,total_paise,shipping_name,shipping_phone,idempotency_key) values (%s,1,0,1,'n','p',%s)",
                  role="service_role", params=(a, "key-" + str(a)))
    ok("database constraints reject bad data even from the backend: stock < 0, bad enums, double-used payment id, duplicate idempotency key")


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="cdiab_pg_")
    srv = pgserver.get_server(tmp)
    uri = srv.get_uri()
    rc = 1
    try:
        print("Applying stub + migrations + seed on PostgreSQL ...")
        with psycopg.connect(uri, autocommit=True) as conn:
            for f in [DB / "tests" / "supabase_stub.sql", *sorted((DB / "migrations").glob("*.sql")), DB / "seed.sql"]:
                conn.execute(f.read_text(encoding="utf-8"))
                print(f"  applied {f.name}")
            print("RLS / storage / constraint checks:")
            checks(conn)
        print(f"\n{len(passed)} database check groups passed. Running the backend suite on this SQL schema ...")
        env = {**os.environ, "TEST_DATABASE_URL": uri.replace("postgresql://", "postgresql+psycopg://", 1)}
        rc = subprocess.call([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "app/tests"], cwd=ROOT / "backend", env=env)
    finally:
        srv.cleanup()
    return rc


if __name__ == "__main__":
    sys.exit(main())
