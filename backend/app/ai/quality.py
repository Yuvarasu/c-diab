from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class QualityThresholds:
    min_side: int = 480
    min_blur: float = 25.0
    min_brightness: float = 45.0
    max_brightness: float = 215.0
    min_contrast: float = 12.0


def assess_quality(img: Image.Image, t: QualityThresholds = QualityThresholds()) -> dict:
    """Heuristic photo checks (size, blur, light). They gate analysis; they are not clinical measurements."""
    w, h = img.size
    g = img.convert("L")
    scale = 640 / max(w, h)
    if scale < 1:
        g = g.resize((max(3, int(w * scale)), max(3, int(h * scale))), Image.LANCZOS)
    a = np.asarray(g, dtype=np.float32)
    lap = a[1:-1, 1:-1] * -4 + a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:]
    blur, bright, contrast = float(lap.var()), float(a.mean()), float(a.std())
    issues: list[dict] = []
    if min(w, h) < t.min_side:
        issues.append({"code": "too_small", "message": "The photo resolution is too low."})
    if blur < t.min_blur:
        issues.append({"code": "blurry", "message": "The photo looks blurry. Hold the phone steady and tap to focus."})
    if bright < t.min_brightness:
        issues.append({"code": "too_dark", "message": "The photo is too dark. Use brighter, even light."})
    elif bright > t.max_brightness:
        issues.append({"code": "too_bright", "message": "The photo is overexposed. Avoid direct flash or glare."})
    if contrast < t.min_contrast and not any(i["code"] in ("too_dark", "too_bright") for i in issues):
        issues.append({"code": "low_contrast", "message": "The photo has very little detail. Move closer and use good light."})
    return {"ok": not issues, "blur_score": round(blur, 1), "brightness": round(bright, 1),
            "width": w, "height": h, "issues": issues}
