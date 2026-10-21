import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
import requests

from .base import (
    AIAuthenticationError,
    AIConfigurationError,
    AIModelNotFoundError,
    AINetworkError,
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

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_API_URL = "https://openrouter.ai/api/v1/models/user"
DEFAULT_OPENROUTER_PLACEHOLDER = "PASTE_YOUR_OPENROUTER_API_KEY_HERE"
DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b-20260604"


class OpenRouterProvider(BaseAIProvider):
    """
    OpenRouter API client implementing the official OpenAI-compatible chat completions standard.
    Serves as the final fallback provider in the multi-tier AI system.

    Official OpenRouter API details:
    - Endpoint: https://openrouter.ai/api/v1/chat/completions
    - Auth: Bearer <OPENROUTER_API_KEY>
    - Optional discovery headers: HTTP-Referer, X-Title

    Model selection:
    - Entirely configured through OPENROUTER_MODEL in .env
    - Verified models include:
        * meta-llama/llama-3.3-70b-instruct (paid, high performance, cost-effective)
        * google/gemini-2.0-flash-001 (paid, fast multimodal)
        * deepseek/deepseek-chat (paid, high reasoning)
        * openrouter/free (dynamic free-model router, subject to free rate limits)
        * meta-llama/llama-3.1-8b-instruct:free (free variant)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        key_label: str = "OpenRouter",
    ):
        raw_key = (
            api_key
            if api_key is not None
            else getattr(settings, "OPENROUTER_API_KEY", "")
        )
        raw_model = (
            model_name
            if model_name is not None
            else getattr(settings, "OPENROUTER_MODEL", "")
        )

        self.api_key = raw_key.strip() if isinstance(raw_key, str) else ""
        configured_models = (
            get_configured_models("openrouter")
            if model_name is None
            else parse_model_names(raw_model)
        )
        # See GeminiProvider: an explicitly configured but invalid model id must
        # never be silently replaced by a default.
        if configured_models:
            self.model_name = configured_models[0]
        elif model_name is None and getattr(
            settings, "OPENROUTER_MODEL_EXPLICIT", False
        ):
            self.model_name = ""
        else:
            self.model_name = DEFAULT_OPENROUTER_MODEL
        self.key_label = key_label
        self.placeholder_key = getattr(
            settings, "OPENROUTER_PLACEHOLDER_KEY", DEFAULT_OPENROUTER_PLACEHOLDER
        )
        self.timeout = getattr(settings, "AI_TIMEOUT_SECONDS", 60)
        self.max_output_tokens = getattr(settings, "AI_MAX_OUTPUT_TOKENS", 1024)

        if not self.api_key:
            logger.info("OpenRouter key is unconfigured (empty).")
        elif (
            self.api_key != self.api_key.strip("'\"")
            or self.api_key != self.api_key.strip()
        ):
            logger.warning(
                "OPENROUTER_API_KEY contains surrounding quotes or spaces."
            )

    def is_configured(self) -> Tuple[bool, str]:
        """
        Validate whether a legitimate OpenRouter credential and model are configured.
        Returns (is_ready, message) without leaking secret values.
        """
        if not self.api_key:
            return (
                False,
                "OpenRouter API key is missing. Please set OPENROUTER_API_KEY in your .env file.",
            )
        if (
            self.api_key == self.placeholder_key
            or self.api_key.startswith("PASTE_YOUR_OPENROUTER")
        ):
            return (
                False,
                "OpenRouter API key is still set to placeholder. Please update your .env file with your key from https://openrouter.ai/keys.",
            )
        if len(self.api_key) < 15 or not self.api_key.startswith("sk-or-"):
            return (
                False,
                "OpenRouter API key appears invalid (keys start with 'sk-or-'). Please check OPENROUTER_API_KEY in your .env file.",
            )
        if not self.model_name or not re.fullmatch(r"^[A-Za-z0-9_.\-:/]+$", self.model_name):
            return (
                False,
                "OpenRouter model configuration is invalid. Check OPENROUTER_MODEL.",
            )
        try:
            from importlib.util import find_spec
            sdk_available = find_spec("requests") is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            sdk_available = False
        if not sdk_available:
            return False, "The requests library is unavailable. Install project requirements."
        return True, f"OpenRouter provider is properly configured (model={self.model_name})."

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://sarkariresult.local",
            "X-Title": "Sarkari Result AI Assistant",
        }
        return headers

    def list_models(self, timeout: int = 8) -> List[Dict[str, str]]:
        is_ready, message = self.is_configured()
        if not is_ready:
            raise AIProviderError(message, provider="openrouter")

        try:
            response = requests.get(
                OPENROUTER_MODELS_API_URL,
                headers=self._build_headers(),
                timeout=timeout,
            )
        except requests.Timeout as exc:
            raise AIProviderTimeoutError(
                "OpenRouter model discovery timed out. Please retry.",
                provider="openrouter",
            ) from exc
        except requests.RequestException as exc:
            raise AIServerError(
                "Could not connect to OpenRouter to load available models.",
                provider="openrouter",
            ) from exc

        if response.status_code != 200:
            if response.status_code in (401, 403):
                message = "OpenRouter rejected the configured API key while loading models."
            elif response.status_code == 429:
                message = "OpenRouter model discovery is rate limited. Please retry shortly."
            elif response.status_code >= 500:
                message = "OpenRouter model discovery is temporarily unavailable."
            else:
                message = f"OpenRouter model discovery failed (HTTP {response.status_code})."
            raise AIProviderError(
                message,
                provider="openrouter",
                status_code=response.status_code,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise AIProviderError(
                "OpenRouter returned an invalid model-list response.",
                provider="openrouter",
            ) from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("data", []), list):
            raise AIProviderError(
                "OpenRouter returned an invalid model-list response.",
                provider="openrouter",
            )

        models = []
        for model in payload.get("data", []):
            if not isinstance(model, dict):
                continue
            model_id = model.get("id")
            architecture = model.get("architecture")
            output_modalities = (
                architecture.get("output_modalities", [])
                if isinstance(architecture, dict)
                else []
            )
            if (
                isinstance(model_id, str)
                and model_id
                and isinstance(output_modalities, list)
                and "text" in output_modalities
            ):
                models.append(
                    {"id": model_id, "label": model.get("name") or model_id}
                )
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
        Send conversation turns to OpenRouter chat completions endpoint.
        Returns cleaned assistant response text.
        """
        is_ready, err = self.is_configured()
        if not is_ready:
            raise AIConfigurationError(err, provider="openrouter")

        effective_timeout = timeout if timeout is not None else self.timeout
        selected_model = model_name or self.model_name

        formatted_messages = []
        if system_instruction:
            formatted_messages.append({"role": "system", "content": system_instruction})

        for msg in messages:
            role = msg.get("role", "user")
            if role == "model":
                role = "assistant"
            elif role not in ("user", "assistant", "system"):
                role = "user"
            content = str(msg.get("content", "")).strip()
            if content:
                formatted_messages.append({"role": role, "content": content})

        if not formatted_messages:
            raise ValueError("No message content provided.")

        payload = {
            "model": selected_model,
            "messages": formatted_messages,
            "temperature": 0.4,
            "max_tokens": max_output_tokens or self.max_output_tokens,
        }

        logger.info(
            "OpenRouter API call starting (model=%s, timeout=%ss).",
            selected_model,
            effective_timeout,
        )

        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers=self._build_headers(),
                json=payload,
                timeout=effective_timeout,
            )
        except requests.Timeout as e:
            logger.warning("OpenRouter API request timed out (%s).", type(e).__name__)
            raise AIProviderTimeoutError(
                "The OpenRouter assistant request timed out. Please try again.",
                provider="openrouter",
            ) from e
        except requests.RequestException as e:
            logger.error("OpenRouter network request failed (%s).", type(e).__name__)
            raise AINetworkError(
                "Network connection to OpenRouter failed. Please try again later.",
                provider="openrouter",
            ) from e

        status_code = response.status_code

        # Successful response
        if status_code == 200:
            try:
                data = response.json()
            except ValueError as e:
                logger.error("OpenRouter returned invalid JSON.")
                raise AIServerError("OpenRouter returned malformed response.", provider="openrouter") from e

            choices = data.get("choices", [])
            reply = ""
            if choices and isinstance(choices, list):
                first_choice = choices[0]
                if isinstance(first_choice, dict):
                    msg_obj = first_choice.get("message", {})
                    if isinstance(msg_obj, dict):
                        reply = msg_obj.get("content", "")

            reply = (reply or "").strip()
            if not reply:
                logger.warning("OpenRouter API returned an empty response body.")
                raise RuntimeError("AI provider returned no response.")

            # Ensure API key is never exposed in output text
            if self.api_key:
                reply = reply.replace(self.api_key, "[redacted]")
            return reply

        # Classify HTTP error responses
        try:
            err_data = response.json()
            err_obj = err_data.get("error", {})
            err_msg = (
                err_obj.get("message", "")
                if isinstance(err_obj, dict)
                else str(err_data)
            )
        except Exception:
            err_msg = response.text[:200]

        logger.error(
            "OpenRouter API call returned HTTP %d (model=%s).",
            status_code,
            selected_model,
        )

        if status_code in (401, 403):
            raise AIAuthenticationError(
                "Invalid OpenRouter API key. Please verify OPENROUTER_API_KEY in your .env file.",
                provider="openrouter",
                status_code=status_code,
            )
        elif status_code == 402:
            raise AIPaymentRequiredError(
                "OpenRouter account has insufficient credits or requires payment setup.",
                provider="openrouter",
                status_code=402,
            )
        elif status_code == 404:
            raise AIModelNotFoundError(
                "OpenRouter did not recognize the selected model ID.",
                provider="openrouter",
                status_code=404,
            )
        elif status_code == 400 and any(
            marker in err_msg.lower()
            for marker in ("model not found", "model is not supported", "unsupported model", "no endpoints found")
        ):
            raise AIModelNotFoundError(
                "OpenRouter explicitly rejected or did not support the selected model.",
                provider="openrouter",
                status_code=400,
            )
        elif status_code == 429:
            error_lower = err_msg.lower()
            if any(
                marker in error_lower
                for marker in ("quota exhausted", "quota exceeded", "insufficient quota", "credits exhausted")
            ):
                raise AIQuotaExceededError(
                    "OpenRouter explicitly reported exhausted quota or credits.",
                    provider="openrouter",
                    status_code=429,
                )
            raise AIRateLimitError(
                "OpenRouter returned HTTP 429 due to rate limiting.",
                provider="openrouter",
                status_code=429,
            )
        elif 500 <= status_code < 600:
            raise AIServerError(
                f"OpenRouter upstream service temporarily unavailable (HTTP {status_code}).",
                provider="openrouter",
                status_code=status_code,
            )
        else:
            raise AIProviderError(
                f"OpenRouter request failed (HTTP {status_code}).",
                provider="openrouter",
                status_code=status_code,
            )

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

        effective_timeout = timeout if timeout is not None else min(self.timeout, 15)

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

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a JSON-only data extractor. Return only valid JSON, no markdown.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 256,
        }

        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers=self._build_headers(),
                json=payload,
                timeout=effective_timeout,
            )
            if response.status_code == 200:
                data = response.json()
                raw = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
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
                        if k
                        in (
                            "keyword",
                            "organization",
                            "qualification",
                            "location",
                            "category",
                        )
                        and v
                    }
        except Exception as e:
            logger.warning("OpenRouter query interpretation fallback (%s).", type(e).__name__)
        return {}
