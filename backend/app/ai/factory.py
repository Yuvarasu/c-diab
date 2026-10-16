from app.ai.base import InferenceBackend
from app.ai.demo import DemoInference
from app.ai.http_model import HttpInference
from app.core.config import Settings


def build_inference(s: Settings) -> InferenceBackend:
    if s.ai_backend == "http":
        return HttpInference(s.model_service_url, s.model_service_token)
    if s.is_production:  # defence in depth; Settings already refuses this
        raise RuntimeError("Demo AI is not available in production")
    return DemoInference(s.demo_force_outcome)
