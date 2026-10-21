import json
import logging
import re
from importlib.util import find_spec
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings

from .base import (
    AIAuthenticationError,
    AIModelNotFoundError,
    AINetworkError,
    AIPaymentRequiredError,
    AIProviderError,
    AIProviderTimeoutError,
    AIQuotaExceededError,
    AIRateLimitError,
    AIServerError,
    BaseAIProvider,
)
from .model_config import get_configured_models, parse_model_names

logger = logging.getLogger(__name__)

# Stable GA models from OpenAI - verified from official documentation
# Reference: https://developers.openai.com/api/docs/models/gpt-4o-mini
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class OpenAIProvider(BaseAIProvider):
    """
    OpenAI API implementation using the official OpenAI Python SDK.
    Follows official security standards:
    - Never prints or exposes the API key in logs, exceptions, or responses.
    - Accurately detects missing and placeholder keys.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        raw_key = (
            api_key if api_key is not None else getattr(settings, "OPENAI_API_KEY", "")
        )
        self.api_key = raw_key.strip() if isinstance(raw_key, str) else ""
        # See GeminiProvider: an explicitly configured but invalid model id must
        # never be silently replaced by a default.
        if model_name is not None:
            # Bound to one registry account: use exactly the selected model id.
            parsed = parse_model_names(model_name)
            self.model_name = parsed[0] if parsed else ""
        else:
            configured_models = get_configured_models("openai")
            if configured_models:
                self.model_name = configured_models[0]
            elif getattr(settings, "OPENAI_MODEL_EXPLICIT", False):
                self.model_name = ""
            else:
                self.model_name = DEFAULT_OPENAI_MODEL
        self.placeholder_key = getattr(
            settings, "OPENAI_PLACEHOLDER_KEY", "PASTE_YOUR_OPENAI_API_KEY_HERE"
        )
        self.timeout = getattr(settings, "AI_TIMEOUT_SECONDS", 60)
        self.max_output_tokens = getattr(settings, "AI_MAX_OUTPUT_TOKENS", 1024)
        self._client = None

        # Diagnostic logging without exposing the API key
        if not self.api_key:
            logger.warning("OPENAI_API_KEY is empty — check that .env exists and is loaded by config/settings/base.py.")
        elif self.api_key != self.api_key.strip('"\'') or self.api_key != self.api_key.strip():
            logger.warning("OPENAI_API_KEY contains surrounding quotes or spaces — clean up the .env line formatting.")
        if not self.model_name:
            logger.warning("OPENAI_MODEL is explicitly set but contains no valid model id — check the .env line.")
        logger.info("OpenAI provider initialized (model=%s, key_configured=%s).", self.model_name, bool(self.api_key))

    def is_configured(self) -> Tuple[bool, str]:
        """
        Validates whether a legitimate OpenAI API key is configured.
        Returns (is_ready, message) without leaking the actual key value.
        """
        if not self.api_key:
            return (
                False,
                "OpenAI API key is missing. Please open the .env file and paste your key from https://platform.openai.com/api-keys.",
            )
        if self.api_key == self.placeholder_key:
            return (
                False,
                "OpenAI API key is still set to the default placeholder. Please update your .env file with your real key from https://platform.openai.com/api-keys.",
            )
        if len(self.api_key) < 20:
            return (
                False,
                "OpenAI API key appears too short or invalid. Please check your .env file.",
            )
        # OpenAI keys start with 'sk-'
        if not self.api_key.startswith("sk-"):
            return (
                False,
                "OpenAI API key should start with 'sk-'. Please check your .env file.",
            )
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,149}", self.model_name or ""):
            return (
                False,
                "OpenAI model configuration is invalid. Check OPENAI_MODEL.",
            )
        try:
            sdk_available = find_spec("openai") is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            sdk_available = False
        if not sdk_available:
            return False, "The OpenAI Python SDK is unavailable. Install with: pip install openai"
        return (True, "OpenAI provider is properly configured.")

    def _get_client(self):
        if self._client is None:
            is_ready, err = self.is_configured()
            if not is_ready:
                raise ValueError(err)
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key, timeout=self.timeout)
            except Exception as e:
                logger.error(
                    "Failed to initialize OpenAI client (%s).",
                    type(e).__name__,
                )
                raise RuntimeError("Failed to initialize AI provider client.")
        return self._client

    def list_models(self, timeout: int = 8) -> List[Dict[str, str]]:
        is_ready, message = self.is_configured()
        if not is_ready:
            raise AIProviderError(message, provider="openai")

        try:
            response = self._get_client().models.list(timeout=timeout)
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code == 401 or status_code == 403:
                message = "OpenAI rejected the configured API key while loading models."
            elif status_code == 429:
                message = "OpenAI model discovery is rate limited. Please retry shortly."
            elif "timeout" in type(exc).__name__.lower():
                raise AIProviderTimeoutError(
                    "OpenAI model discovery timed out. Please retry.",
                    provider="openai",
                ) from exc
            else:
                message = "Could not load available models from OpenAI."
            raise AIProviderError(
                message,
                provider="openai",
                status_code=status_code,
            ) from exc

        non_chat_markers = (
            "embedding",
            "whisper",
            "tts",
            "dall-e",
            "moderation",
            "transcribe",
            "realtime",
        )
        models = []
        for model in getattr(response, "data", []):
            model_id = getattr(model, "id", "")
            if (
                isinstance(model_id, str)
                and model_id
                and not any(marker in model_id.lower() for marker in non_chat_markers)
            ):
                models.append({"id": model_id, "label": model_id})
        return sorted(models, key=lambda model: model["id"])

    def generate_chat_response(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        timeout: Optional[int] = None,
        model_name: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
    ) -> str:
        """
        Sends conversation history to OpenAI and returns the assistant's response.
        """
        # Use instance timeout if not provided
        effective_timeout = timeout if timeout is not None else self.timeout
        selected_model = model_name or self.model_name

        client = self._get_client()

        # Map roles to OpenAI format (user, assistant, system)
        formatted_messages = []
        if system_instruction:
            formatted_messages.append({"role": "system", "content": system_instruction})

        for msg in messages:
            role = msg.get("role", "user")
            # Map our internal role names to OpenAI's expected format
            if role == "model":
                role = "assistant"
            elif role not in ("user", "assistant", "system"):
                role = "user"

            content = str(msg.get("content", "")).strip()
            if content:
                formatted_messages.append({"role": role, "content": content})

        if not formatted_messages:
            raise ValueError("No message content provided.")

        logger.info(
            "OpenAI API call starting (model=%s, timeout=%s).",
            selected_model,
            effective_timeout,
        )

        try:
            response = client.chat.completions.create(
                model=selected_model,
                messages=formatted_messages,
                temperature=0.4,
                max_tokens=max_output_tokens or self.max_output_tokens,
                timeout=effective_timeout,
            )

            reply = response.choices[0].message.content if response.choices else ""
            reply = (reply or "").strip()

            if not reply:
                logger.warning("OpenAI API returned an empty response.")
                raise RuntimeError("AI provider returned no response.")

            logger.info("OpenAI API call succeeded (model=%s).", selected_model)
            return reply

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error("OpenAI API call failed (%s).", error_type)
            status_code = getattr(e, "status_code", None)
            message_lower = error_msg.lower()
            if "timeout" in error_type.lower() or "timeout" in message_lower:
                raise AIProviderTimeoutError(
                    "OpenAI request timed out.",
                    provider="openai",
                    status_code=status_code,
                ) from e
            if status_code in (401, 403) or "invalid api key" in message_lower:
                raise AIAuthenticationError(
                    "OpenAI rejected the configured API key.",
                    provider="openai",
                    status_code=status_code or 401,
                ) from e
            if status_code == 402 or any(
                marker in message_lower
                for marker in ("quota exhausted", "quota exceeded", "insufficient quota", "credits exhausted")
            ):
                raise AIQuotaExceededError(
                    "OpenAI explicitly reported exhausted quota or credits.",
                    provider="openai",
                    status_code=status_code,
                ) from e
            if status_code == 429 or "rate limit" in message_lower:
                raise AIRateLimitError(
                    "OpenAI returned HTTP 429 due to rate limiting.",
                    provider="openai",
                    status_code=status_code or 429,
                ) from e
            if status_code == 404 or "model not found" in message_lower:
                raise AIModelNotFoundError(
                    "OpenAI did not recognize the selected model ID.",
                    provider="openai",
                    status_code=status_code or 404,
                ) from e
            if status_code in (408, 502, 503, 504) or (
                isinstance(status_code, int) and 500 <= status_code < 600
            ):
                raise AIServerError(
                    "OpenAI returned an upstream server or gateway error.",
                    provider="openai",
                    status_code=status_code,
                ) from e
            if any(
                marker in error_type.lower()
                for marker in ("connection", "network", "connect")
            ):
                raise AINetworkError(
                    "Network connectivity to OpenAI failed.",
                    provider="openai",
                ) from e
            raise AIProviderError(
                "OpenAI request failed without a classifiable provider status.",
                provider="openai",
                status_code=status_code,
            ) from e

    def parse_job_query(
        self,
        query: str,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Parses a natural-language search query into structured search filter criteria.
        Returns a dict with keys: keyword, organization, qualification, location, category.
        """
        is_ready, _ = self.is_configured()
        if not is_ready:
            return {}

        # Use instance timeout if not provided
        effective_timeout = timeout if timeout is not None else self.timeout

        prompt = (
            "You are a search query interpreter for an Indian Government Jobs website (Sarkari Result).\n"
            "Given the user's search text, extract the intended search parameters into a JSON object.\n"
            "Fields must be:\n"
            "- keyword: general topic or exam name (e.g., 'CGL', 'Clerk', 'Constable', or empty string)\n"
            "- organization: recruitment body (e.g., 'SSC', 'UPSC', 'RRB', 'IBPS', or empty string)\n"
            "- qualification: required degree or schooling (e.g., '10th', '12th', 'Graduate', 'B.Tech', or empty string)\n"
            "- location: state or region (e.g., 'Delhi', 'Uttar Pradesh', 'Bihar', or empty string)\n"
            "- category: job field (e.g., 'Railway', 'Defence', 'Police', 'Banking', 'Teaching', 'Central', 'State', or empty string)\n"
            "Return ONLY valid JSON with no markdown backticks.\n\n"
            f"User search query: {query}"
        )

        try:
            client = self._get_client()

            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a JSON-only data extractor. Return only valid JSON, no markdown."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=256,
                response_format={"type": "json_object"},
                timeout=effective_timeout,
            )

            raw = response.choices[0].message.content if response.choices else ""
            raw = (raw or "").strip()

            # Clean up markdown code blocks if returned
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]

            parsed = json.loads(raw.strip())
            if isinstance(parsed, dict):
                return {
                    k: str(v).strip()
                    for k, v in parsed.items()
                    if k in ("keyword", "organization", "qualification", "location", "category")
                    and v
                }
        except Exception as e:
            logger.warning("AI query interpretation fallback (%s).", type(e).__name__)
        return {}
