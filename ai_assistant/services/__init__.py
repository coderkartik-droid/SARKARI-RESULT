from django.conf import settings

from . import availability, model_config
from .base import AIProviderError, BaseAIProvider
from .gemini_provider import GeminiProvider
from .grok_provider import GrokProvider
from .model_config import get_model_configuration
from .openai_provider import OpenAIProvider
from .openrouter_provider import OpenRouterProvider


def _configured_provider_name() -> str:
    provider_name = getattr(settings, "AI_PROVIDER", "gemini")
    if not isinstance(provider_name, str):
        return ""
    return provider_name.strip().lower()


class UnsupportedAIProvider(BaseAIProvider):
    """Safe, explicit result for an unknown provider configuration."""

    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        self.message = (
            "The configured AI provider is not supported. Set AI_PROVIDER to "
            "'gemini', 'openai', 'openrouter', or 'grok' in .env."
        )

    def is_configured(self):
        return False, self.message

    def list_models(self, timeout=8):
        raise AIProviderError(self.message, provider=self.provider_name)

    def generate_chat_response(
        self, messages, system_instruction=None, timeout=15, model_name=None, max_output_tokens=None
    ):
        raise RuntimeError(self.message)

    def parse_job_query(self, query, timeout=10):
        raise RuntimeError(self.message)


def get_ai_provider(provider_name=None, api_key=None, model_name=None) -> BaseAIProvider:
    """Return a provider bound to one configuration.

    ``api_key`` and ``model_name`` select a specific registered account/model.
    When they are omitted the provider falls back to the project settings, which
    keeps the single-account call sites (and the job-search parser) unchanged.
    """
    provider_name = provider_name or _configured_provider_name()
    provider_name = provider_name.strip().lower() if isinstance(provider_name, str) else ""
    if provider_name == "gemini":
        return GeminiProvider(api_key=api_key, model_name=model_name)
    elif provider_name == "openai":
        return OpenAIProvider(api_key=api_key, model_name=model_name)
    elif provider_name == "openrouter":
        return OpenRouterProvider(api_key=api_key, model_name=model_name)
    elif provider_name == "grok":
        return GrokProvider(api_key=api_key, model_name=model_name)
    return UnsupportedAIProvider(provider_name)


def get_available_models(provider=None):
    """Return every registered provider/model configuration.

    A configuration whose credentials are unusable still appears in the list:
    hiding it would make a missing key look like a missing model.
    """
    models, _ = get_model_configuration()
    credentials = {entry["id"]: entry["api_key"] for entry in model_config.get_registry()}
    for model in models:
        model_provider = get_ai_provider(
            model["provider"],
            api_key=credentials.get(model["id"]),
            model_name=model["model"],
        )
        is_ready, message = model_provider.is_configured()
        if is_ready:
            model.update(
                {
                    "configured": True,
                    "status": "unknown",
                    "availability": availability.label_for("unknown"),
                    "message": "Availability has not been checked.",
                }
            )
        else:
            missing_key = not bool(getattr(model_provider, "api_key", ""))
            status = "missing_api_key" if missing_key else "not_configured"
            model.update(
                {
                    "configured": False,
                    "status": status,
                    "availability": availability.label_for(status),
                    "message": message,
                }
            )
    return models


def get_ai_status() -> dict:
    """
    Returns public/safe AI status information without ever leaking secrets.
    """
    is_enabled = getattr(settings, "AI_ENABLED", False)
    provider_name = _configured_provider_name()
    provider = get_ai_provider()
    is_ready, config_message = provider.is_configured()
    if provider_name not in ("gemini", "openai", "openrouter", "grok"):
        provider_name = "unsupported"
    model_name = getattr(provider, "model_name", "")
    if not isinstance(model_name, str) or not model_name.isascii() or len(model_name) > 150:
        model_name = ""
    if getattr(provider, "api_key", "") and getattr(provider, "api_key", "") in model_name:
        model_name = ""

    return {
        "enabled": bool(is_enabled),
        "configured": is_ready,
        "provider": provider_name,
        "model": model_name,
        "message": config_message if is_enabled else "AI assistant is currently disabled in settings (AI_ENABLED=False).",
    }
