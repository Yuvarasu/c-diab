# C-Diab: Care for Every Step.

Android app for **AI-assisted diabetic foot screening** and a **therapeutic-footwear shop**, built as a college project.
React Native + Expo (custom dev build, **no Expo Go**) · FastAPI · Supabase (Auth, PostgreSQL + RLS, private Storage).

> **Screening is not diagnosis.** The AI shipped here is a **labelled demo simulator**, not a clinical model. See `docs/ai_model.md` and `docs/privacy_and_safety.md`.

```
mobile/     Expo Router app (TypeScript), EAS profiles, tests
backend/    FastAPI service: policy, screening, orders, payments, admin/clinical, tests, scripts
database/   SQL migrations (schema, RLS, storage), seed, Supabase stub for tests
docs/       architecture · setup · api · ai_model · privacy_and_safety · android_build · play_store_release
```

## Run it (local demo, about 10 minutes): details in `docs/setup.md`
```powershell
# backend: Windows PowerShell (macOS/Linux commands are in docs/setup.md)
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.demo.example .env       # set SUPABASE_URL inside
python -m app.seed
python -m uvicorn app.main:create_app --factory --reload --port 8000     # then open http://127.0.0.1:8000/health
```
```bash
# mobile: build the custom dev client once (docs/android_build.md), then
cd mobile && npm install && npx expo start --dev-client
```

## What is implemented
| Area | State |
|---|---|
| Auth (register, login, logout, reset email, session persistence, expiry handling) | Implemented; needs your Supabase project |
| Health profile, consent records (screening consents + separate optional AI-training consent) | Implemented, enforced on the server |
| Screening: questionnaire with instant urgent advice, camera/gallery, upload progress, quality gate, report, history | Implemented end to end |
| AI | **Demo simulator (labelled)** + validated HTTP model interface. No clinical model included |
| Server-side purchase gate: screening freshness, ownership, clinician review, never-eligible outcomes, production policy approval | Implemented and tested |
| Shop: catalogue, variants/sizes, server cart, stock reservation, shipping, checkout, idempotent orders, order history | Implemented |
| Payments | **Mock provider (dev)** with the real verification path; **Razorpay server integration written but untested without keys**; the native Razorpay checkout SDK is **not** integrated in the app yet |
| Admin: products, stock, prices, orders, status workflow, analytics, review routing (no photo access) | Implemented |
| Clinical reviewer: assigned queue, case view, decision, audit log | Implemented |
| Privacy: consent management, data export, account + health-data deletion | Implemented |
| Android config: `com.cdiab.app`, EAS dev/preview/prod, minimal permissions, icons | Configured; **builds not run** (needs your Expo login) |

## Verified here
* Backend: **121 tests passing**; the same suite passes on a **real PostgreSQL** built from the SQL migrations, plus RLS/storage/constraint checks (`backend/scripts/pg_verify.py`).
* **Full journey over real HTTP** against a running server (`backend/scripts/e2e_smoke.py`, 14 checks).
* Mobile: TypeScript 0 errors (typed routes enforced), **27 tests**, Android Metro/Hermes bundle export succeeds, `expo prebuild` manifest reviewed.
* **Not verified:** running on a physical phone, a live Supabase project (incl. JWKS verification), Razorpay, EAS builds, Play Console.

## Still needed before real patients or the Play Store
Clinician-approved policy and a validated model · regulatory classification · real privacy policy, support contact, deletion web page · Razorpay keys + native checkout (or keep payments off) · HTTPS hosting for the API · real product copy/photos · device testing. Full list: `docs/privacy_and_safety.md`, `docs/play_store_release.md`.
