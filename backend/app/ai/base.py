from dataclasses import dataclass, field
from typing import Literal, Optional, Protocol

from app.domain import Side


class InferenceError(Exception):
    """The model could not produce a valid result."""


@dataclass
class ModelResult:
    wound_detected: Optional[bool]  # None = model could not decide
    category: Optional[Literal["superficial", "deep"]]  # None = model does not grade severity
    confidence: Optional[float]  # only when legitimately provided by a validated model
    model_name: str
    model_version: str
    is_demo: bool
    notes: list[str] = field(default_factory=list)


class InferenceBackend(Protocol):
    name: str

    def analyze(self, images: dict[Side, bytes]) -> ModelResult: ...
