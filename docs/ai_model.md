# AI screening: how it works and what is NOT claimed

## Honest scope
No clinically validated model ships with this repository. The shipped model is a **demo simulator** that looks at nothing
medical: it picks an outcome from a hash of the image bytes (or from `DEMO_FORCE_OUTCOME`) and **never invents a
confidence number**. Every result it produces carries `is_demo = true` and the banner
**"DEMO RESULT — NOT A MEDICAL ASSESSMENT"** on the report, history, clinician view and checkout.

Production **cannot** use it: `Settings` refuses to start with `APP_ENV=production` and the demo AI, and `build_inference` refuses again.
A general-purpose vision model must not be used as if it were a validated ulcer-staging system.

## Pipeline
| Stage | Status |
|---|---|
| Image quality (size, sharpness, brightness, contrast) | **Implemented** (`ai/quality.py`). Failing photos give an *inconclusive* result and the model is not called. Thresholds are heuristics: calibrate `QUALITY_MIN_BLUR` with real photos. |
| Possible-wound detection | Interface ready; **needs a validated model** |
| Localization / segmentation | Not implemented (add only if the model provides it) |
| Severity category (`superficial` / `deep`) | Optional. Used only if the model returns it. A wound without a category → *clinical review required* |
| Uncertainty | Implemented: `wound_detected = null`, missing category, optional `min_model_confidence` floor in the policy file, model errors → inconclusive / `503`, never "normal" |

## Plugging in a real model
Run it as a separate service and set `AI_BACKEND=http`, `MODEL_SERVICE_URL`, `MODEL_SERVICE_TOKEN`.
```
POST <MODEL_SERVICE_URL>        Authorization: Bearer <token>
multipart/form-data: left=<jpeg>, right=<jpeg>
200 {"wound_detected": true|false|null, "category": "superficial"|"deep"|null,
     "confidence": 0.0-1.0|null, "model_name": "...", "model_version": "..."}
```
The response is schema-validated (`ai/http_model.py`): `category` requires `wound_detected = true`, confidence must be 0–1, names are required. Anything else raises `InferenceError` → `503 ai_unavailable`, the screening is marked failed and can be retried. Show `confidence` only if the validated model really reports a calibrated one.

## Before using it with real people (outside the code)
* A qualified clinician defines the outcome categories and the eligibility policy, and signs `policy/*.json` (`approved_by`, `approved_on`).
* The model is validated on data representative of your users (skin tones, lighting, devices) with sensitivity / specificity measured for the **intended use**, and the numbers are documented here. Do not publish accuracy figures you have not measured.
* Training on user photos needs separate consent (`ai_training`), ethics/data-use approval and de-identification. Nothing in this repository trains on user data.
* Decide, with a regulatory professional, whether the software is a medical device in your market (see `play_store_release.md`).
