# Google Play release guide

> Google's requirements change. The points marked **(verified 13 Oct 2026)** were checked against Google's pages that day; re-check before submitting.
> Approval is never guaranteed.

## 0. Read this first: is C-Diab a "medical device"?
Google's Health apps declaration distinguishes apps **regulated as medical devices** ("diagnostic tools, treatment recommendation systems…") from other health apps. Regulated apps must be declared as such and **provide proof of approval/clearance on request**; other health apps must say in the description that the app is **not a medical device and does not diagnose, treat, cure, or prevent any medical condition**, and must remind users to consult a healthcare professional. *(verified 13 Oct 2026)*

An AI that looks at photos of feet for possible wounds may be regulated software in India (CDSCO), the EU (MDR) or elsewhere. **This is a regulatory decision for you and a regulatory professional, not something this repository can settle.** Do not publish with the "not a medical device" wording unless that is true. Until then: use closed/internal testing, label everything as a demonstration, and keep the demo AI banner visible.

## 1. Hard requirements checklist
| Requirement | Status |
|---|---|
| **Target API 36** for new apps/updates *(verified)* | React Native 0.86 defaults to 36; confirm on the built file (`android_build.md`) |
| **Health apps declaration** (Play Console → Policy → App content) *(verified)* | You complete it (select *Medical* / *Medical device* accurately) |
| **Privacy policy URL** describing handling of personal and sensitive data *(verified)* | **You provide.** `mobile/src/app/legal.tsx` is only a draft |
| In-app disclaimer + store-description disclaimer, "consult a healthcare professional" *(verified)* | In-app: done on every screening screen. Store text: drafted below |
| Camera used for a health function → state **device compatibility** in the description *(verified)* | Drafted below (needs a rear camera); add models you tested |
| **Data safety** form | Table below |
| **Account deletion**: users who can create an account must be able to delete it, in the app and via a web link (confirm the current policy text) | In-app done; **you** provide a web deletion-request URL |
| Developer contact details, support email, business/legal identity | **You provide.** None are invented here |
| Content rating, target audience (18+ is assumed by the terms), ads declaration (none) | You complete |
| New personal developer accounts may have to run a closed test with a minimum number of testers for a minimum period before production | Check the current rule in your Play Console |

## 2. Data safety form: what the app actually handles
| Data type | Collected | Why | Notes |
|---|---|---|---|
| Name, email, phone (optional), delivery address | yes | account, delivery | in Supabase (auth) and orders |
| Health info: diabetes details (optional), symptom answers, screening results | yes | app function | optional profile; consent recorded |
| Photos: foot photos | yes | app function (screening) | private storage, EXIF removed, deletable |
| Purchase history | yes | orders | retained for legal reasons after account deletion |
| Payment card details | **no** | | handled by the payment provider (Razorpay) |
| Location, contacts, SMS, microphone, device IDs, advertising ID | **no** | | permissions are blocked in the manifest |
| Encrypted in transit | yes in production (HTTPS) | | enforce HTTPS on the API |
| Deletion | in-app + you add a web link | | |
Decide carefully how to answer "shared with third parties" for your hosting/Supabase/Razorpay processors using Google's definitions; this depends on your contracts.

## 3. Listing text (drafts: edit, do not rely on legal wording)
**Name (≤30):** `C-Diab: Foot Health Screening`
**Short description (≤80):** `AI-assisted foot check, guidance and footwear shop. Not a medical diagnosis.`
**Full description:**
> C-Diab helps people with diabetes keep an eye on their feet and find suitable footwear.
>
> • Answer a short questionnaire about your feet and get clear guidance, including when to seek care.
> • Take a photo of each foot for an AI-assisted screening and read a plain-language report.
> • Review past reports, manage your consents, export or delete your data.
> • Browse and order footwear after completing a screening.
>
> **Important:** C-Diab is [a screening aid. Choose ONE wording that matches your regulatory position: "not a medical device and does not diagnose, treat, cure, or prevent any medical condition" OR the medical-device declaration]. A photograph cannot reliably show the severity of an ulcer or rule out infection. Always consult a qualified healthcare professional about your health, and seek urgent care if you notice warning signs.
>
> Requires an Android phone with a rear camera. Tested on: [list the devices you tested].
**Release notes (1.0.0):** `First release: foot-health questionnaire, AI-assisted photo screening with reports, footwear shop, order history, privacy controls.`

## 4. Graphics
* App icon 512×512: `docs/store/icon-512.png` (draft generated from the launcher icon).
* Feature graphic 1024×500: `docs/store/feature-graphic-draft.png` (draft; replace with your final artwork).
* Screenshots (min. 2, phone): welcome · home · screening intro (disclaimer visible) · questionnaire · photo capture · report · shop · product · privacy & consent. **Do not use screenshots of simulated results as if they were real**: capture report screens only from a build wired to a validated model, or leave them out.

## 5. Test checklist before each release
Install from the `preview`/internal-track build on at least two real phones (different Android versions/screen sizes) and run:
register → email confirm → login → logout → session survives restart · consent switches · questionnaire (try an urgent answer: advice appears *before* photos) · camera permission allow / deny / "don't ask again" · gallery pick · retake / remove / retry on bad network · blurry photo → inconclusive · report (historical banner on older ones) · shop → cart → stock limits → checkout blocked without screening → allowed after screening/clinician approval · failed payment is not "paid" · order history · data export · account deletion · airplane mode banner · TalkBack on the main flow · font size 200% · rotate/background/foreground during upload.
Run `pytest`, `scripts/pg_verify.py`, `npm test`, `npm run typecheck` on the release commit.

## 6. Sources checked (13 Oct 2026)
* Target API level requirements: https://support.google.com/googleplay/android-developer/answer/11926878
* Health apps declaration: https://support.google.com/googleplay/android-developer/answer/14738291
* Health & medical apps policy: https://support.google.com/googleplay/android-developer/answer/16679511
