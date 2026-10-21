import re
from importlib.util import find_spec

from django.conf import settings
from django.core.checks import Warning, register


@register()
def check_ai_configuration(app_configs, **kwargs):
    if not getattr(settings, "AI_ENABLED", False):
        return []

    provider = getattr(settings, "AI_PROVIDER", "gemini")
    if not isinstance(provider, str) or provider.strip().lower() not in ("gemini", "openai", "openrouter", "grok"):
        return [
            Warning(
                "AI is enabled, but AI_PROVIDER is unsupported. Configure AI_PROVIDER to gemini, openai, openrouter, or grok.",
                hint="Set AI_PROVIDER to a supported provider or disable AI_ENABLED.",
                id="ai_assistant.W001",
            )
        ]

    normalized_provider = provider.strip().lower()
    errors = []

    if normalized_provider == "gemini":
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        placeholder_key = getattr(
            settings, "GEMINI_PLACEHOLDER_KEY", "PASTE_YOUR_GEMINI_API_KEY_HERE"
        )
        if (
            not isinstance(api_key, str)
            or not api_key.strip()
            or api_key.strip() == placeholder_key
            or len(api_key.strip()) < 10
        ):
            errors.append(
                Warning(
                    "AI is enabled, but Gemini credentials are missing or invalid.",
                    hint="Set a valid GEMINI_API_KEY or disable AI_ENABLED.",
                    id="ai_assistant.W002",
                )
            )

        model = getattr(settings, "GEMINI_MODEL", "")
        if not isinstance(model, str) or (
            model.strip()
            and any(
                not re.fullmatch(
                    r"(?:models/)?[A-Za-z0-9][A-Za-z0-9._-]{0,149}",
                    candidate.strip(),
                )
                for candidate in model.split(",")
            )
        ):
            errors.append(
                Warning(
                    "AI is enabled, but GEMINI_MODEL is invalid.",
                    hint="Set GEMINI_MODEL to a model identifier or leave it blank for the default.",
                    id="ai_assistant.W003",
                )
            )

        try:
            sdk_available = find_spec("google.genai") is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            sdk_available = False
        if not sdk_available:
            errors.append(
                Warning(
                    "AI is enabled, but the Google GenAI SDK is unavailable.",
                    hint="Install the declared project requirements or disable AI_ENABLED.",
                    id="ai_assistant.W004",
                )
            )

    elif normalized_provider == "openai":
        api_key = getattr(settings, "OPENAI_API_KEY", "")
        placeholder_key = getattr(
            settings, "OPENAI_PLACEHOLDER_KEY", "PASTE_YOUR_OPENAI_API_KEY_HERE"
        )
        if (
            not isinstance(api_key, str)
            or not api_key.strip()
            or api_key.strip() == placeholder_key
            or len(api_key.strip()) < 20
            or not api_key.strip().startswith("sk-")
        ):
            errors.append(
                Warning(
                    "AI is enabled, but OpenAI credentials are missing or invalid.",
                    hint="Set a valid OPENAI_API_KEY (starts with sk-) or disable AI_ENABLED.",
                    id="ai_assistant.W005",
                )
            )

        model = getattr(settings, "OPENAI_MODEL", "")
        if not isinstance(model, str) or (
            model.strip()
            and any(
                not re.fullmatch(r"^[A-Za-z0-9_.\-:/]+$", candidate.strip())
                for candidate in model.split(",")
            )
        ):
            errors.append(
                Warning(
                    "AI is enabled, but OPENAI_MODEL is invalid.",
                    hint="Set OPENAI_MODEL to a valid model identifier or leave it blank for the default.",
                    id="ai_assistant.W006",
                )
            )

        try:
            sdk_available = find_spec("openai") is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            sdk_available = False
        if not sdk_available:
            errors.append(
                Warning(
                    "AI is enabled, but the OpenAI SDK is unavailable.",
                    hint="Install the declared project requirements or disable AI_ENABLED.",
                    id="ai_assistant.W007",
                )
            )

    elif normalized_provider == "openrouter":
        api_key = getattr(settings, "OPENROUTER_API_KEY", "")
        placeholder_key = getattr(
            settings, "OPENROUTER_PLACEHOLDER_KEY", "PASTE_YOUR_OPENROUTER_API_KEY_HERE"
        )
        if (
            not isinstance(api_key, str)
            or not api_key.strip()
            or api_key.strip() == placeholder_key
            or len(api_key.strip()) < 15
            or not api_key.strip().startswith("sk-or-")
        ):
            errors.append(
                Warning(
                    "AI is enabled, but OpenRouter credentials are missing or invalid.",
                    hint="Set a valid OPENROUTER_API_KEY (starts with sk-or-) or disable AI_ENABLED.",
                    id="ai_assistant.W008",
                )
            )

        model = getattr(settings, "OPENROUTER_MODEL", "")
        if not isinstance(model, str) or (
            model.strip()
            and any(
                not re.fullmatch(r"^[A-Za-z0-9_.\-:/]+$", candidate.strip())
                for candidate in model.split(",")
            )
        ):
            errors.append(
                Warning(
                    "AI is enabled, but OPENROUTER_MODEL is invalid.",
                    hint="Set OPENROUTER_MODEL to a valid model identifier or leave it blank for the default.",
                    id="ai_assistant.W009",
                )
            )

        try:
            sdk_available = find_spec("requests") is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            sdk_available = False
        if not sdk_available:
            errors.append(
                Warning(
                    "AI is enabled, but the requests library is unavailable.",
                    hint="Install the declared project requirements or disable AI_ENABLED.",
                    id="ai_assistant.W010",
                )
            )

    elif normalized_provider == "grok":
        api_key = getattr(settings, "GROK_API_KEY", "")
        placeholder_key = getattr(
            settings, "GROK_PLACEHOLDER_KEY", "PASTE_YOUR_GROK_API_KEY_HERE"
        )
        if (
            not isinstance(api_key, str)
            or len(api_key.strip()) < 10
            or api_key.strip() == placeholder_key
            or not re.fullmatch(r"[A-Za-z0-9_-]{10,}", api_key.strip())
        ):
            errors.append(
                Warning(
                    "AI is enabled, but Grok credentials are missing or invalid.",
                    hint="Set a valid GROK_API_KEY or disable AI_ENABLED.",
                    id="ai_assistant.W011",
                )
            )

        model = getattr(settings, "GROK_MODEL", "")
        if not isinstance(model, str) or (
            model.strip()
            and any(
                not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,149}", candidate.strip())
                for candidate in model.split(",")
            )
        ):
            errors.append(
                Warning(
                    "AI is enabled, but GROK_MODEL is invalid.",
                    hint="Set GROK_MODEL to a model identifier or leave it blank for the default.",
                    id="ai_assistant.W012",
                )
            )

        try:
            requests_available = find_spec("requests") is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            requests_available = False
        if not requests_available:
            errors.append(
                Warning(
                    "AI is enabled, but the requests library is unavailable.",
                    hint="Install the declared project requirements or disable AI_ENABLED.",
                    id="ai_assistant.W013",
                )
            )

    return errors
