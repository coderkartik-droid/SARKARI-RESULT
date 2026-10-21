import json
import logging
import re
from importlib.util import find_spec
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from httpx import TimeoutException
import requests

from .base import (
    AIAuthenticationError,
    AIModelNotFoundError,
    AIQuotaExceededError,
    AIProviderError,
    AIProviderTimeoutError,
    AIRateLimitError,
    AIServerError,
    BaseAIProvider,
)
from .model_config import get_configured_models, parse_model_names

logger = logging.getLogger(__name__)

# Fallback default model if not explicitly specified in settings.
# Keep this a VALID, production-ready flash model (verified against the
# Generative Language API list); deprecated names fail instantly.
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
GEMINI_MODELS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(BaseAIProvider):
    """
    Official Google Gemini API implementation using the google-genai SDK.
    Follows official security standards:
    - Never prints or exposes the API key in logs, exceptions, or responses.
    - Accurately detects missing and placeholder keys.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        raw_key = (
            api_key if api_key is not None else getattr(settings, "GEMINI_API_KEY", "")
        )
        self.api_key = raw_key.strip() if isinstance(raw_key, str) else ""
        # The configured allowlist is the only source of model IDs. A default is
        # substituted only when the user never configured a model at all; an
        # explicitly configured-but-invalid entry must surface as an error
        # rather than silently running a different model.
        if model_name is not None:
            # Bound to one registry account: use exactly the id the registry
            # selected, never a default and never another account's model.
            parsed = parse_model_names(model_name)
            self.model_name = parsed[0] if parsed else ""
        else:
            configured_models = get_configured_models("gemini")
            if configured_models:
                self.model_name = configured_models[0]
            elif getattr(settings, "GEMINI_MODEL_EXPLICIT", False):
                self.model_name = ""
            else:
                self.model_name = DEFAULT_GEMINI_MODEL
        self.placeholder_key = getattr(
            settings, "GEMINI_PLACEHOLDER_KEY", "PASTE_YOUR_GEMINI_API_KEY_HERE"
        )
        # Applied when a caller does not pass an explicit cap. Without this the
        # generation call would read a non-existent attribute and fail.
        self.max_output_tokens = getattr(settings, "AI_MAX_OUTPUT_TOKENS", 1024)
        self.timeout = getattr(settings, "AI_TIMEOUT_SECONDS", 60)
        self._client = None

        # Diagnostic logging: makes misconfiguration visible in the console
        # (quotes/spaces from a badly formatted .env, wrong model name, etc.)
        # without ever printing the API key itself.
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is empty — check that .env exists and is loaded by config/settings/base.py.")
        elif self.api_key != self.api_key.strip('"\'') or self.api_key != self.api_key.strip():
            logger.warning("GEMINI_API_KEY contains surrounding quotes or spaces — clean up the .env line formatting.")
        if not self.model_name:
            logger.warning("GEMINI_MODEL is explicitly set but contains no valid model id — check the .env line.")
        logger.info("Gemini provider initialized (model=%s, key_configured=%s).", self.model_name, bool(self.api_key))

    def is_configured(self) -> Tuple[bool, str]:
        """
        Validates whether a legitimate Gemini API key is configured.
        Returns (is_ready, message) without leaking the actual key value.
        """
        if not self.api_key:
            return (
                False,
                "Gemini API key is missing. Please open the .env file and paste your key from https://aistudio.google.com/.",
            )
        if self.api_key == self.placeholder_key:
            return (
                False,
                "Gemini API key is still set to the default placeholder. Please update your .env file with your real key from https://aistudio.google.com/.",
            )
        if len(self.api_key) < 10:
            return (
                False,
                "Gemini API key appears too short or invalid. Please check your .env file.",
            )
        if not re.fullmatch(
            r"(?:models/)?[A-Za-z0-9][A-Za-z0-9._-]{0,149}",
            self.model_name,
        ):
            return False, "Gemini model configuration is invalid. Check GEMINI_MODEL."
        try:
            sdk_available = find_spec("google.genai") is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            sdk_available = False
        if not sdk_available:
            return False, "The Google GenAI SDK is unavailable. Install project requirements."
        return (True, "Gemini provider is properly configured.")

    def _get_client(self):
        if self._client is None:
            is_ready, err = self.is_configured()
            if not is_ready:
                raise ValueError(err)
            try:
                from google import genai

                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(
                    "Failed to initialize Google GenAI client (%s).",
                    type(e).__name__,
                )
                raise RuntimeError("Failed to initialize AI provider client.")
        return self._client

    def list_models(self, timeout: int = 8) -> List[Dict[str, str]]:
        is_ready, message = self.is_configured()
        if not is_ready:
            raise AIProviderError(message, provider="gemini")

        models = []
        page_token = ""
        try:
            while True:
                params = {"key": self.api_key, "pageSize": 100}
                if page_token:
                    params["pageToken"] = page_token
                response = requests.get(
                    GEMINI_MODELS_API_URL,
                    params=params,
                    timeout=timeout,
                )
                if response.status_code != 200:
                    if response.status_code == 401 or response.status_code == 403:
                        message = "Gemini rejected the configured API key while loading models."
                    elif response.status_code == 429:
                        message = "Gemini model discovery is rate limited. Please retry shortly."
                    elif response.status_code >= 500:
                        message = "Gemini model discovery is temporarily unavailable."
                    else:
                        message = f"Gemini model discovery failed (HTTP {response.status_code})."
                    raise AIProviderError(
                        message,
                        provider="gemini",
                        status_code=response.status_code,
                    )

                payload = response.json()
                if not isinstance(payload, dict):
                    raise AIProviderError(
                        "Gemini returned an invalid model-list response.",
                        provider="gemini",
                    )
                provider_models = payload.get("models", [])
                if not isinstance(provider_models, list):
                    raise AIProviderError(
                        "Gemini returned an invalid model-list response.",
                        provider="gemini",
                    )
                for model in provider_models:
                    if not isinstance(model, dict):
                        continue
                    name = model.get("name", "")
                    supported = model.get("supportedGenerationMethods", [])
                    if (
                        isinstance(name, str)
                        and name.startswith("models/")
                        and "generateContent" in supported
                    ):
                        model_id = name.removeprefix("models/")
                        models.append(
                            {
                                "id": model_id,
                                "label": model.get("displayName") or model_id,
                            }
                        )
                page_token = payload.get("nextPageToken", "")
                if not page_token:
                    break
        except requests.Timeout as exc:
            raise AIProviderTimeoutError(
                "Gemini model discovery timed out. Please retry."
            ) from exc
        except requests.RequestException as exc:
            raise AIProviderError(
                "Could not connect to Gemini to load available models.",
                provider="gemini",
            ) from exc
        except (ValueError, TypeError) as exc:
            raise AIProviderError(
                "Gemini returned an invalid model-list response.",
                provider="gemini",
            ) from exc
        return sorted(models, key=lambda model: model["id"])

    def _generate_content(self, contents, config, model_name=None):
        """
        Send a generate_content request to the selected model.

        The exact model the caller asked for is always used. There is no silent
        fallback to another model: a failure must be reported against the model
        the user selected so the availability status stays truthful.

        Returns the raw API response. Never logs secrets or request contents.
        """
        from google.genai import errors as genai_errors

        client = self._get_client()
        selected_model = model_name or self.model_name
        logger.info("Gemini API call starting (model=%s).", selected_model)
        try:
            response = client.models.generate_content(
                model=selected_model,
                contents=contents,
                config=config,
            )
            logger.info("Gemini API call succeeded (model=%s).", selected_model)
            return response
        except genai_errors.APIError as e:
            logger.error(
                "Gemini API call failed (model=%s, status=%s, type=%s). Check "
                "GEMINI_API_KEY / GEMINI_MODEL in .env (unquoted, no stray "
                "spaces) and the model id against the Generative Language API "
                "model list.",
                selected_model,
                getattr(e, "code", None),
                type(e).__name__,
            )
            raise

    def generate_chat_response(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        timeout: int = 15,
        model_name: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
    ) -> str:
        """
        Sends conversation history to Gemini and returns the assistant's response.
        """
        from google.genai import types

        # Build contents from messages
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            # Map roles: Google GenAI expects 'user' or 'model'
            if role in ("assistant", "model"):
                genai_role = "model"
            else:
                genai_role = "user"
            content_text = str(msg.get("content", "")).strip()
            if content_text:
                contents.append(
                    types.Content(
                        role=genai_role,
                        parts=[types.Part.from_text(text=content_text)],
                    )
                )

        if not contents:
            raise ValueError("No message content provided.")

        thinking_config = None
        if hasattr(types, "ThinkingConfig") and hasattr(types, "ThinkingLevel"):
            thinking_config = types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.MEDIUM
            )

        config_kwargs = {
            "temperature": 0.4,
            "max_output_tokens": max_output_tokens or self.max_output_tokens,
            "http_options": types.HttpOptions(timeout=timeout * 1000),
        }
        if thinking_config is not None:
            config_kwargs["thinking_config"] = thinking_config
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        config = types.GenerateContentConfig(**config_kwargs)

        try:
            response = self._generate_content(contents, config, model_name=model_name)
            reply = getattr(response, "text", "")
            if not reply and getattr(response, "candidates", None):
                # Fallback to extract text from candidate parts if needed
                for candidate in response.candidates:
                    if candidate.content and candidate.content.parts:
                        reply = "".join(
                            getattr(p, "text", "")
                            for p in candidate.content.parts
                            if not getattr(p, "thought", False)
                        )
                        break
            reply = (reply or "").strip()
            if not reply:
                logger.warning("Gemini API returned an empty response.")
                raise RuntimeError("AI provider returned no response.")
            if self.api_key:
                reply = reply.replace(self.api_key, "[redacted]")
            return reply
        except (TimeoutException, TimeoutError) as e:
            logger.warning("Gemini API request timed out (%s).", type(e).__name__)
            raise AIProviderTimeoutError(
                "The AI assistant request timed out. Please try again."
            ) from e
        except Exception as e:
            # Keep provider diagnostics from exposing request details or secrets.
            err_msg = str(e)
            status_code = getattr(e, "code", None)
            logger.error(
                "Gemini API call failed (%s%s).",
                type(e).__name__,
                f" status={status_code}" if status_code is not None else "",
            )
            err_lower = err_msg.lower()
            if any(
                marker in err_lower
                for marker in ("quota exceeded", "quota exhausted", "daily quota", "insufficient quota")
            ):
                raise AIQuotaExceededError(
                    "Gemini explicitly reported exhausted quota.",
                    provider="gemini",
                    status_code=429 if status_code == 429 else status_code,
                ) from e
            if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                raise AIRateLimitError(
                    "Gemini returned HTTP 429 due to rate limiting.",
                    provider="gemini",
                    status_code=429,
                ) from e
            if "API_KEY_INVALID" in err_msg or ("400" in err_msg and "key" in err_msg.lower()):
                raise AIAuthenticationError(
                    "Invalid Gemini API key. Please verify GEMINI_API_KEY in configuration.",
                    provider="gemini",
                    status_code=status_code if isinstance(status_code, int) else 401,
                ) from e
            if status_code in (401, 403):
                raise AIAuthenticationError(
                    "Gemini rejected the configured API key.",
                    provider="gemini",
                    status_code=status_code,
                ) from e
            if status_code == 404:
                raise AIModelNotFoundError(
                    "Gemini did not recognize the selected model ID.",
                    provider="gemini",
                    status_code=404,
                ) from e
            if status_code in (408, 504):
                raise AIProviderTimeoutError(
                    "Gemini request timed out upstream.",
                    provider="gemini",
                    status_code=status_code,
                ) from e
            if isinstance(status_code, int) and status_code >= 500:
                raise AIServerError(
                    "Gemini upstream service is temporarily unavailable.",
                    provider="gemini",
                    status_code=status_code,
                ) from e
            raise RuntimeError("AI service temporarily unavailable. Please try again later.")

    def parse_job_query(
        self,
        query: str,
        timeout: int = 10,
    ) -> Dict[str, Any]:
        """
        Parses a natural-language search query into structured search filter criteria.
        Returns a dict with keys: keyword, organization, qualification, location, category.
        """
        is_ready, _ = self.is_configured()
        if not is_ready:
            return {}

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
            from google.genai import types

            response = self._generate_content(
                prompt,
                types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=256,
                    response_mime_type="application/json",
                    http_options=types.HttpOptions(timeout=timeout * 1000),
                ),
            )
            raw = (getattr(response, "text", "") or "").strip()
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
