from typing import Literal, Optional

import httpx
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.ai.base import InferenceError, ModelResult
from app.domain import Side


class ModelServiceResponse(BaseModel):
    wound_detected: Optional[bool]
    category: Optional[Literal["superficial", "deep"]] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)
    model_name: str = Field(min_length=1, max_length=80)
    model_version: str = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def _consistent(self):
        if self.category and not self.wound_detected:
            raise ValueError("category requires wound_detected=true")
        return self


class HttpInference:
    """Calls a separately deployed, validated model service. Output is schema-validated before use."""
    name = "http"

    def __init__(self, url: str, token: str = "", timeout: float = 25.0):
        self.url, self.token, self.timeout = url, token, timeout

    def analyze(self, images: dict[Side, bytes]) -> ModelResult:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        files = {side.value: (f"{side.value}.jpg", data, "image/jpeg") for side, data in images.items()}
        try:
            r = httpx.post(self.url, files=files, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            parsed = ModelServiceResponse.model_validate(r.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise InferenceError(f"model service failed: {type(exc).__name__}") from exc
        return ModelResult(parsed.wound_detected, parsed.category, parsed.confidence, parsed.model_name,
                           parsed.model_version, is_demo=False)
