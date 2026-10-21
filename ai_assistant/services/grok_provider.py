import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import requests
from django.conf import settings

from .base import (
    AIAuthenticationError,
    AINetworkError,
    AIModelNotFoundError,
    AIPaymentRequiredError,
    AIQuotaExceededError,
    AIProviderError,
    AIProviderTimeoutError,
    AIRateLimitError,
    AIServerError,
    BaseAIProvider,
)
from .model_config import get_configured_models, parse_model_names

logger = logging.getLogger(__name__)
SAFE_PROVIDER_ERROR_FIELD = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

GROK_API_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_GROK_MODEL = "grok-4.7"
GROK_CHAT_MODELS = {
    "grok-4.7": "Grok 4.7 (latest)",
    "grok-4.6": "Grok 4.6",
    "grok-4.3": "Grok 4.3",
}


class GrokProvider(BaseAIProvider):
    """xAI Grok chat completions provider using the OpenAI-compatible API."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        raw_key = api_key if api_key is not None else getattr(settings, "GROK_API_KEY", "")
        self.api_key = raw_key.strip() if isinstance(raw_key, str) else ""
        # See GeminiProvider: an explicitly configured but invalid model id must
        # never be silently replaced by a default.
        if model_name is not None:
            # Bound to one registry account: use exactly the selected model id.
            parsed = parse_model_names(model_name)
            self.model_name = parsed[0] if parsed else ""
        else:
            configured_models = get_configured_models("grok")
            if configured_models:
                self.model_name = configured_models[0]
            elif getattr(settings, "GROK_MODEL_EXPLICIT", False):
                self.model_name = ""
            else:
                self.model_name = DEFAULT_GROK_MODEL
        self.timeout = getattr(settings, "AI_TIMEOUT_SECONDS", 60)
        self.max_output_tokens = getattr(settings, "AI_MAX_OUTPUT_TOKENS", 1024)

    def is_configured(self) -> Tuple[bool, str]:
        if not self.api_key:
            return False, "Grok API key is missing. Set GROK_API_KEY in your .env file."
        if self.api_key == getattr(settings, "GROK_PLACEHOLDER_KEY", "PASTE_YOUR_GROK_API_KEY_HERE"):
            return False, "Grok API key is still set to the default placeholder."
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,}", self.api_key):
            return False, "Grok API key format appears invalid. Check GROK_API_KEY."
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,149}", self.model_name):
            return False, "Grok model configuration is invalid. Check GROK_MODEL."
        return True, "Grok provider is properly configured."

    def list_models(self, timeout: int = 8) -> List[Dict[str, str]]:
        return [{"id": model_id, "label": model_id} for model_id in get_configured_models("grok")]

    def _completion(self, messages, model_name, timeout, max_output_tokens=None):
        ready, message = self.is_configured()
        if not ready:
            raise ValueError(message)
        payload = {
            "model": model_name or self.model_name,
            "messages": messages,
            "temperature": 0.4,
            "max_tokens": max_output_tokens or self.max_output_tokens,
        }
        try:
            response = requests.post(
                GROK_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout or self.timeout,
            )
        except requests.Timeout as error:
            logger.warning("Grok API request timed out (%s).", type(error).__name__)
            raise AIProviderTimeoutError(
                "The Grok assistant request timed out. Please try again.",
                provider="grok",
                status_code=408,
            ) from error
        except requests.RequestException as error:
            logger.warning("Grok network request failed (%s).", type(error).__name__)
            raise AINetworkError(
                "Network connection to Grok failed.", provider="grok"
            ) from error

        if response.status_code == 429:
            try:
                error_data = response.json()
                error_value = error_data.get("error", {})
                error_message = (
                    error_value.get("message", "")
                    if isinstance(error_value, dict)
                    else str(error_value)
                ).lower()
            except (ValueError, AttributeError, TypeError):
                error_message = ""
            if any(
                marker in error_message
                for marker in ("quota exhausted", "quota exceeded", "insufficient quota", "credits exhausted")
            ):
                raise AIQuotaExceededError(
                    "Grok explicitly reported exhausted quota or credits.",
                    provider="grok",
                    status_code=429,
                )
            logger.warning("Grok API rate limit reached (model=%s).", payload["model"])
            raise AIRateLimitError(
                "Grok API rate limit reached.", provider="grok", status_code=429
            )
        if response.status_code in (401, 403):
            logger.error("Grok API rejected credentials (HTTP %d).", response.status_code)
            raise AIAuthenticationError(
                "Grok rejected the configured API key.",
                provider="grok",
                status_code=response.status_code,
            )
        if response.status_code == 402:
            raise AIPaymentRequiredError(
                "Grok account requires payment or has insufficient credits.",
                provider="grok",
                status_code=402,
            )
        if response.status_code == 404:
            raise AIModelNotFoundError(
                "Grok did not recognize the selected model ID.",
                provider="grok",
                status_code=404,
            )
        if response.status_code == 400:
            try:
                error_data = response.json()
                error_value = error_data.get("error", {})
                error_message = (
                    error_value.get("message", "")
                    if isinstance(error_value, dict)
                    else str(error_value)
                ).lower()
            except (ValueError, AttributeError, TypeError):
                error_data = {}
                error_value = {}
                error_message = ""
            provider_error_code = (
                error_value.get("code")
                if isinstance(error_value, dict)
                else None
            )
            provider_error_type = (
                error_value.get("type")
                if isinstance(error_value, dict)
                else None
            )
            safe_error_fields = {}
            if isinstance(provider_error_code, (str, int)):
                provider_error_code = str(provider_error_code)
                if SAFE_PROVIDER_ERROR_FIELD.fullmatch(provider_error_code):
                    safe_error_fields["provider_error_code"] = provider_error_code
            if isinstance(provider_error_type, str) and SAFE_PROVIDER_ERROR_FIELD.fullmatch(
                provider_error_type
            ):
                safe_error_fields["provider_error_type"] = provider_error_type
            classification_evidence = " ".join(
                (
                    error_message,
                    safe_error_fields.get("provider_error_code", "").lower(),
                    safe_error_fields.get("provider_error_type", "").lower(),
                )
            )
            if any(
                marker in classification_evidence
                for marker in ("model not found", "model_not_found", "unsupported model", "no endpoints found")
            ):
                error = AIModelNotFoundError(
                    "Grok explicitly rejected or did not support the selected model.",
                    provider="grok",
                    status_code=400,
                )
                error.provider_error_code = safe_error_fields.get("provider_error_code")
                error.provider_error_type = safe_error_fields.get("provider_error_type")
                raise error
            raise AIProviderError(
                "Grok rejected the request without classifiable model evidence.",
                provider="grok",
                status_code=400,
                **safe_error_fields,
            )
        if 500 <= response.status_code < 600:
            raise AIServerError(
                "Grok returned an upstream server or gateway error.",
                provider="grok",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise AIProviderError(
                "Grok request failed without a classifiable provider status.",
                provider="grok",
                status_code=response.status_code,
            )
        try:
            data = response.json()
            reply = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            logger.error("Grok API returned an invalid completion response.")
            raise AIProviderError(
                "Grok returned an invalid completion response.",
                provider="grok",
                status_code=response.status_code,
                provider_error_type="malformed_response",
            ) from error
        if not isinstance(reply, str) or not reply.strip():
            raise AIProviderError(
                "Grok returned an empty completion response.",
                provider="grok",
                status_code=response.status_code,
                provider_error_type="empty_response",
            )
        return reply.strip().replace(self.api_key, "[redacted]")

    def generate_chat_response(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        timeout: int = 15,
        model_name: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
    ) -> str:
        formatted_messages = []
        if system_instruction:
            formatted_messages.append(
                {"role": "system", "content": system_instruction}
            )
        for message in messages:
            role = message.get("role", "user")
            if role in ("assistant", "model"):
                role = "assistant"
            else:
                role = "user"
            content = str(message.get("content", "")).strip()
            if content:
                formatted_messages.append({"role": role, "content": content})
        if not formatted_messages:
            raise ValueError("No message content provided.")
        return self._completion(
            formatted_messages,
            model_name=model_name,
            timeout=timeout,
            max_output_tokens=max_output_tokens,
        )

    def parse_job_query(
        self,
        query: str,
        timeout: int = 10,
    ) -> Dict[str, Any]:
        prompt = (
            "Extract job search filters from this query as JSON with only these "
            "string keys: keyword, organization, qualification, location, category. "
            "Return JSON only.\n\n"
            f"Query: {query}"
        )
        try:
            response = self._completion(
                [{"role": "user", "content": prompt}],
                model_name=self.model_name,
                timeout=timeout,
            )
            parsed = json.loads(response)
        except (RuntimeError, ValueError, json.JSONDecodeError):
            logger.warning("Grok job-query interpretation failed; using local parsing.")
            return {}
        if not isinstance(parsed, dict):
            return {}
        allowed = {"keyword", "organization", "qualification", "location", "category"}
        return {
            key: str(value).strip()[:80]
            for key, value in parsed.items()
            if key in allowed and isinstance(value, (str, int, float)) and str(value).strip()
        }
