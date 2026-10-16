# Architecture

```
 Android app (React Native + Expo dev build)            Supabase                         FastAPI backend
 ┌──────────────────────────────────────┐     ┌──────────────────────────┐     ┌─────────────────────────────────────┐
 │ Expo Router screens, TanStack Query  │────▶│ Auth (email + password)  │     │ JWT verification (HS256 or JWKS)    │
 │ session in SecureStore               │     │ PostgreSQL + RLS         │◀────│ roles read from the DATABASE        │
 │ no secrets, no medical rules         │     │ private Storage bucket   │     │ screening policy + eligibility      │
 └───────────────┬──────────────────────┘     └──────────────────────────┘     │ images / AI / orders / payments     │
                 │  Bearer <Supabase access token>                              │ audit log, rate limits              │
                 └─────────────────────────────────────────────────────────────▶│                                     │
                                                                                └──────┬───────────────┬──────────────┘
                                                                                       ▼               ▼
                                                                          AI inference interface   Payment provider
                                                                          (demo | HTTP model)      (mock | Razorpay)
```

**One rule drives the design: the app is not trusted.** The phone only displays things and collects input. Every
decision that matters (who you are, what you may see, whether you may buy, what a price is, whether a payment happened)
is made by the backend and, as a second layer, the database.

## Components
| Part | Where | Responsibility |
|---|---|---|
| Mobile app | `mobile/` | UI, camera/gallery, forms. Holds only the user's session token. |
| Backend | `backend/app/` | All business rules and authorization. Connects to Postgres with a server credential. |
| Database | `database/migrations/` | Schema, constraints, RLS, private storage rules. |
| Screening policy | `backend/app/screening_policy/` + `backend/policy/*.json` | Symptom triage, outcome rules, product eligibility. Pure functions, unit tested. |
| AI layer | `backend/app/ai/` | Image-quality gate, replaceable inference interface, labelled demo model. |
| Payments | `backend/app/payments/` | Provider abstraction, signature + webhook verification. |

## Who can see what
| Data | Customer | Admin | Clinical reviewer |
|---|---|---|---|
| Own profile, health profile, consents | yes | no | no |
| Own screenings, **photos**, reports | yes | **no, never** | only cases **assigned** to them (pseudonymous reference, no name/email); every view is audit-logged |
| Product catalogue | read | create / edit / stock / price | no |
| Orders | own | all (needs delivery address to fulfil) | no |
| Routing reviews to clinicians | no | yes (sees case id, date, outcome only) | no |
| Audit log | no | no (database only) | no |

Roles live in `profiles.role` and can only be changed with SQL by whoever administers the database. They are **never**
read from the token (a user can edit their own metadata) and no endpoint or RLS policy lets a user change them.

## Screening flow
1. **Consent**: `health_data_processing` and `image_screening` must both be granted (append-only `consent_records`; withdrawing blocks further processing). `ai_training` is a separate, optional consent.
2. **Questionnaire** → `POST /screenings`. The backend triages the answers *immediately* (`routine` / `caution` / `urgent`) and returns safety guidance before any photo is requested. "Not sure" counts as concerning, never as "no".
3. **Photos** → `POST /screenings/{id}/images` (one per foot). The server validates by content (not the declared type), enforces size/format/dimension limits, strips EXIF/GPS by re-encoding, measures sharpness/light, stores the file under a server-generated path in a private bucket.
4. **Analysis** → `POST /screenings/analyze`. Urgent triage short-circuits to an urgent warning. Otherwise: missing photos → `422`; poor photos → `inconclusive_image` **without** calling the model; model failure → `503` and the screening is marked failed (never "normal"). The model output is validated, then the policy maps it to an outcome.
5. **Report** → outcome, plain-language steps, quality, model version, confidence **only if the model supplied one**, clinical-review state, and the server's eligibility decision.

### Outcome rules (`screening_policy/outcome.py`, in this order)
`urgent triage` → urgent warning · unusable photos / no model answer / low confidence → inconclusive · model says deep → possible deeper wound · caution triage → clinical review required · model says superficial → possible superficial wound · wound seen but not gradable → clinical review required · otherwise no obvious wound.

## Purchase gate (`screening_policy/eligibility.py`)
Enforced in `POST /orders/checkout`, on the server, for any product with `requires_screening`. The client cannot supply or override anything.
* **Hard-coded, not configurable:** `urgent_warning`, `possible_deeper_wound` and `inconclusive_image` never unlock footwear, not even with clinician approval. Configuration that tries to list them is rejected at load time.
* Based on the user's **latest** non-failed screening (a newer urgent result cannot be dodged by pointing at an older good one → `409 screening_superseded`).
* Must be completed, fresh (default 30 days), not a demo result unless `ALLOW_DEMO_ELIGIBILITY` (dev only), and, under the strict policy, **approved by an assigned clinician** (`approved_for_footwear`). A clinician `not_suitable` / `needs_in_person_assessment` blocks purchase.
* In **production** every purchase is refused until the policy file carries `approved_by` and `approved_on`: i.e. until a qualified professional has signed it off.

## Orders and payments
Prices, shipping and stock are recomputed from the database at checkout. Stock is reserved when the order is created and released if payment fails or the order is cancelled (the database also has `stock >= 0`). `idempotency_key` + a unique constraint make duplicate requests return the same order. An order is marked paid **only** after the backend verifies the provider's signature, re-fetches the payment from the provider and checks order id and amount; the signed webhook goes through the same path. A used `provider_payment_id` cannot settle a second order.

## Defence in depth
Application checks → database constraints (enums, `stock >= 0`, uniqueness) → RLS (clients read only their own rows and cannot write) → private storage (owner-only reads, no client writes). `scripts/pg_verify.py` proves the last three on a real PostgreSQL.
