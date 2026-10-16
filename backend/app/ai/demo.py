import hashlib
from typing import Optional

from app.ai.base import ModelResult
from app.domain import Side

_FORCED = {
    "none": (False, None),
    "superficial": (True, "superficial"),
    "deep": (True, "deep"),
    "undetermined": (None, None),
}


class DemoInference:
    """DEVELOPMENT ONLY. Deterministic simulated output. It looks at nothing medical and invents no confidence."""
    name = "demo"

    def __init__(self, force: str = ""):
        self.force = force

    def analyze(self, images: dict[Side, bytes]) -> ModelResult:
        if self.force:
            detected, category = _FORCED[self.force]
        else:
            h = hashlib.sha256(b"".join(images[s] for s in sorted(images, key=lambda x: x.value))).digest()
            bucket = int.from_bytes(h[:4], "big") % 100
            detected, category = (False, None) if bucket < 55 else (True, "superficial") if bucket < 80 else \
                (True, "deep") if bucket < 90 else (True, None)
        return ModelResult(wound_detected=detected, category=category, confidence=None,  # type: ignore[arg-type]
                           model_name="cdiab-demo-simulator", model_version="demo-0", is_demo=True,
                           notes=["Simulated output for demonstration only."])
