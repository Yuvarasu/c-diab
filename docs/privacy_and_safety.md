# Privacy and safety design

*This describes how the software behaves. It is not legal or clinical advice, and it is not a substitute for a reviewed privacy policy, a clinician-approved protocol or regulatory advice.*

## Safety behaviours (all tested)
* Not a diagnosis. The required warning appears before photos are requested and on every report.
* Warning symptoms (discharge; open/new wound with redness, warmth or colour change) show medical guidance **before** any photo step and the screening completes as an *urgent warning* without needing photos.
* "Not sure" is never treated as "no". An unreadable photo, a missing model answer or an outage is **inconclusive/failed, never normal**.
* A wound-free photo result says it "does not rule out an ulcer".
* Urgent, deeper-wound and inconclusive results can never unlock footwear. A required clinician review cannot be bypassed from the app.
* Users are never told to remove a wound dressing for a photo, nor to take photos in an unsafe position ("I can't take these photos safely" path).
* Demo results are labelled everywhere and are rejected by production configuration.

## Data inventory
| Data | Purpose | Where | Visible to |
|---|---|---|---|
| Name, email (phone optional) | account, delivery | `profiles` | the user; admin sees delivery name/phone/address on orders |
| Health profile (optional) | context for screening/clinician | `health_profiles` | the user; assigned clinician sees symptoms, not the profile |
| Symptom answers, outcome | screening | `screenings` | the user; assigned clinician |
| Foot photos | screening | private bucket `screening-images`, re-encoded JPEG, EXIF/GPS removed | the user; assigned clinician (audit-logged). **Never admins** |
| Orders, payments (no card data) | fulfilment, legal retention | `orders`, `payments` | the user; admin |
| Consents | proof of consent | `consent_records` (append-only) | the user |
| Audit log | accountability | `audit_logs` (no health details) | database only |

Payment card details never touch this system; the provider handles them.

## User rights in the app (Profile → Privacy & consent)
* See / change consents; withdrawing screening consent blocks further processing.
* **Copy of my data** (`GET /me/data-export`).
* **Delete my account and health data** (`DELETE /me`): deletes screenings, photos (storage objects too), health profile and cart; anonymises the profile; removes the Supabase auth user when the service key is configured. **Order and payment records are kept** for legal/tax reasons (name/address stay on the order; delivery notes are removed). Confirm the retention period with your accountant/lawyer.

## Security controls
HTTPS (deployment), JWT verification with an algorithm allow-list, roles from the database, ownership checks that return "not found" for other people's records, server-generated storage paths, content-based image validation, rate limiting (per process: use a shared store or gateway for several workers), validation errors that never echo submitted values, structured errors, no health data in logs/audit metadata, secrets only in server environment, session tokens in `expo-secure-store`, app-data backup disabled, minimal Android permissions (camera, internet).

## Needs a human before real use
1. Clinician-approved policy (`approved_by` / `approved_on`), and a clinician review process with an SLA.
2. Validated model and documented performance.
3. Regulatory position (medical device or not) for each market.
4. Reviewed privacy policy and terms at a public URL; data-protection assessment under the laws that apply to you (e.g. India's DPDP Act, GDPR if EU users); retention schedule; breach process.
5. A real support contact and a deletion-request web page.
6. Penetration test / security review, backups, monitoring and an incident plan for the hosted backend.
