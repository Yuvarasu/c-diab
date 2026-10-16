# API reference

Base path `/api/v1` (plus `GET /health`). JSON in/out. Interactive docs at `/docs` when **not** in production.
All endpoints except `/health` and the signed webhook need `Authorization: Bearer <Supabase access token>`.

## Conventions
* **Errors** always look like `{"error": {"code": "...", "message": "...", "details": {...}}}`. Validation errors list field names and problems only, never the submitted values.
* **Ownership**: another user's resource returns `404`, the same as a missing one.
* **Money** is in integer paise (`price_paise`, `total_paise`).
* **Idempotency**: `POST /orders/checkout` requires `idempotency_key`; replaying it returns the same order and payment session.
* **Rate limits** (per user, per process): analyze 15/h, photo upload 40/h, checkout 20/h → `429 rate_limited`.
* **Photos** are never public: `GET .../images/{id}/content` streams the bytes only to the owner (or the assigned clinician, audit-logged).

## Notable error codes
`consent_required` · `images_missing` · `file_too_large` / `unsupported_image` / `image_too_small` · `ai_unavailable` (503) ·
`not_eligible` (403, `details.reason_code`: `screening_required`, `screening_incomplete`, `screening_expired`, `urgent_warning`,
`outcome_not_eligible`, `clinical_review_pending`, `clinical_review_declined`, `demo_result_not_eligible`, `policy_not_clinically_approved`) ·
`screening_superseded` (409) · `insufficient_stock` (409) · `invalid_signature` (400) · `payment_not_confirmed` (400).

## Endpoints
| Method | Path | Who can call it |
|---|---|---|
| GET | `/admin/analytics` | admin |
| GET | `/admin/orders` | admin |
| PUT | `/admin/orders/{order_id}/status` | admin |
| GET | `/admin/products` | admin |
| POST | `/admin/products` | admin |
| PATCH | `/admin/products/{product_id}` | admin |
| POST | `/admin/products/{product_id}/variants` | admin |
| GET | `/admin/review-queue` | admin |
| GET | `/admin/reviewers` | admin |
| POST | `/admin/screenings/{screening_id}/assign` | admin |
| PATCH | `/admin/variants/{variant_id}` | admin |
| GET | `/cart` | signed-in user (own data only) |
| PUT | `/cart/items` | signed-in user (own data only) |
| DELETE | `/cart/items/{variant_id}` | signed-in user (own data only) |
| GET | `/clinical/queue` | clinical reviewer |
| GET | `/clinical/screenings/{screening_id}` | clinical reviewer |
| GET | `/clinical/screenings/{screening_id}/images/{image_id}/content` | clinical reviewer |
| POST | `/clinical/screenings/{screening_id}/review` | clinical reviewer |
| GET | `/health` | public |
| GET | `/me` | signed-in user (own data only) |
| PATCH | `/me` | signed-in user (own data only) |
| DELETE | `/me` | signed-in user (own data only) |
| GET | `/me/consents` | signed-in user (own data only) |
| POST | `/me/consents` | signed-in user (own data only) |
| GET | `/me/data-export` | signed-in user (own data only) |
| GET | `/me/health-profile` | signed-in user (own data only) |
| PUT | `/me/health-profile` | signed-in user (own data only) |
| GET | `/orders` | signed-in user (own data only) |
| POST | `/orders/checkout` | signed-in user (own data only) |
| GET | `/orders/{order_id}` | signed-in user (own data only) |
| POST | `/payments/mock/complete` | signed-in user (dev only) |
| POST | `/payments/verify` | signed-in user (own data only) |
| POST | `/payments/webhook` | payment provider (signed) |
| GET | `/products` | signed-in user (own data only) |
| GET | `/products/{product_id}` | signed-in user (own data only) |
| GET | `/screenings` | signed-in user (own data only) |
| POST | `/screenings` | signed-in user (own data only) |
| POST | `/screenings/analyze` | signed-in user (own data only) |
| GET | `/screenings/eligibility` | signed-in user (own data only) |
| GET | `/screenings/{screening_id}` | signed-in user (own data only) |
| DELETE | `/screenings/{screening_id}` | signed-in user (own data only) |
| POST | `/screenings/{screening_id}/images` | signed-in user (own data only) |
| GET | `/screenings/{screening_id}/images/{image_id}/content` | signed-in user (own data only) |
| DELETE | `/screenings/{screening_id}/images/{side}` | signed-in user (own data only) |
