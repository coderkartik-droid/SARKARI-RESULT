"""Model availability checking and status classification.

This service is the single owner of:

* the canonical availability vocabulary that the API and UI display,
* the mapping of provider exceptions onto that vocabulary,
* a versioned, bounded cache of check results.

Provider adapters raise typed errors (see :mod:`ai_assistant.services.base`).
Normalising them here keeps provider-specific HTTP detail inside the adapters
and stops every caller from re-inventing error handling.
"""

import hashlib
import logging
import re
from typing import Any, Dict, Optional, Tuple

from django.core.cache import cache

from .base import (
    AIAuthenticationError,
    AIConfigurationError,
    AIModelNotFoundError,
    AINetworkError,
    AIPaymentRequiredError,
    AIProviderError,
    AIProviderTimeoutError,
    AIQuotaExceededError,
    AIRateLimitError,
    AIServerError,
)

logger = logging.getLogger(__name__)

# Bump whenever the vocabulary, the classification rules or the cached payload
# shape change. Records written by an older implementation can then never be
# read back, which is what keeps stale "unavailable" verdicts from sticking.
CACHE_VERSION = 4
CACHE_NAMESPACE = f"ai-model-status:v{CACHE_VERSION}"

# A successful probe is trusted for a few minutes; a failure is only cached
# briefly so a transient outage is not remembered as a permanent verdict.
SUCCESS_TTL = 300
FAILURE_TTL = 30

# The one-shot probe used to verify a model really generates text.
PROBE_TIMEOUT_SECONDS = 10
PROBE_MAX_OUTPUT_TOKENS = 16
PROBE_MESSAGE = "Reply with OK."
PROBE_SYSTEM_INSTRUCTION = "Respond with OK only."

# The only labels the UI is allowed to show. ``status`` is the stable machine
# code; ``availability`` is the human label derived from it.
STATUS_LABELS = {
    "available": "Available",
    "missing_api_key": "Missing API key",
    "not_configured": "Not configured",
    "authentication_required": "Authentication required",
    "rate_limited": "Rate limited / Quota exceeded",
    "timeout_gateway": "Timeout / Gateway error",
    "request_rejected": "Request rejected",
    "unsupported_model": "Unsupported model",
    "provider_unavailable": "Provider unavailable",
    "unknown": "Unknown",
}

# A provider error field is only echoed back when it is a short, opaque token.
_SAFE_PROVIDER_ERROR_FIELD = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

_QUOTA_EVIDENCE = (
    "quota exhausted",
    "quota exceeded",
    "insufficient quota",
    "credits exhausted",
    "insufficient_credits",
    "resource_exhausted",
)
_MODEL_EVIDENCE = (
    "model not found",
    "model_not_found",
    "unsupported model",
    "no endpoints found",
    "model is not supported",
    "unknown model",
    "does not exist",
)
_RATE_LIMIT_EVIDENCE = ("rate limit", "too many requests", "rate_limit")


def label_for(status: str) -> str:
    """Return the user-facing label for a machine status code."""
    return STATUS_LABELS.get(status, STATUS_LABELS["unknown"])


def _status_result(
    status: str,
    message: str,
    provider: Optional[str] = None,
    http_status: Optional[int] = None,
    error_type: Optional[str] = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "status": status,
        "availability": label_for(status),
        "message": message,
        "provider": provider,
        "http_status": http_status if isinstance(http_status, int) else None,
    }
    if error_type:
        result["error_type"] = error_type
    return result


def classify_provider_error(exc: Exception) -> Dict[str, Any]:
    """Map a provider exception onto a stable, secret-safe availability result.

    The returned ``message`` is always assembled from fixed sentences plus the
    provider name and HTTP status, so a raw upstream payload (which may embed a
    key or request body) can never leak to the client.
    """
    status_code = getattr(exc, "status_code", None)
    provider = getattr(exc, "provider", None)
    message = str(exc).lower()
    error_type = type(exc).__name__
    error_name = error_type.lower()

    has_quota_evidence = any(term in message for term in _QUOTA_EVIDENCE)
    has_model_evidence = any(term in message for term in _MODEL_EVIDENCE)

    if isinstance(exc, (AIQuotaExceededError, AIPaymentRequiredError)):
        status = "rate_limited"
        reason = "The provider reported exhausted quota or credits."
    elif isinstance(exc, AIRateLimitError) or status_code == 429:
        status = "rate_limited"
        reason = "The provider reported a rate limit (HTTP 429)."
    elif isinstance(exc, AIAuthenticationError) or status_code in (401, 403):
        status = "request_rejected"
        reason = "The provider rejected the request because its credentials were refused."
    elif (
        isinstance(exc, AIModelNotFoundError)
        or status_code == 404
        or (status_code == 400 and has_model_evidence)
    ):
        status = "unsupported_model"
        reason = "The provider reported that this model id is not supported."
    elif status_code == 400:
        status = "request_rejected"
        reason = "The provider rejected the request but did not report a model or credential problem."
    elif isinstance(exc, AIProviderTimeoutError) or status_code in (408, 502, 504):
        status = "timeout_gateway"
        reason = "The provider request timed out or hit an upstream gateway error."
    elif isinstance(exc, AIServerError) or (
        isinstance(status_code, int) and status_code >= 500
    ):
        status = "provider_unavailable"
        reason = "The provider reported an upstream service failure."
    elif isinstance(exc, AINetworkError) or any(
        marker in error_name for marker in ("connection", "network", "connect")
    ):
        status = "provider_unavailable"
        reason = "The provider could not be reached over the network."
    elif isinstance(exc, AIConfigurationError):
        status = "not_configured"
        reason = "The provider is not configured correctly on the server."
    elif "timeout" in error_name or isinstance(exc, TimeoutError):
        status = "timeout_gateway"
        reason = "The provider request timed out."
    elif has_quota_evidence:
        status = "rate_limited"
        reason = "The provider reported exhausted quota or credits."
    elif any(term in message for term in _RATE_LIMIT_EVIDENCE):
        status = "rate_limited"
        reason = "The provider reported a rate limit."
    elif has_model_evidence:
        status = "unsupported_model"
        reason = "The provider reported that this model id is not supported."
    else:
        status = "unknown"
        reason = "The provider response did not contain enough evidence to classify the result."

    if isinstance(status_code, int):
        reason = f"{reason.rstrip('.')} (HTTP {status_code})."

    result = _status_result(
        status,
        reason,
        provider=provider,
        http_status=status_code,
        error_type=error_type,
    )
    for attribute in ("provider_error_code", "provider_error_type"):
        value = getattr(exc, attribute, None)
        if isinstance(value, (str, int)):
            value = str(value)
            if _SAFE_PROVIDER_ERROR_FIELD.fullmatch(value):
                result[attribute] = value
    return result


def cache_key(provider_name: str, model_id: str, provider: Any = None) -> str:
    """Build a versioned cache key bound to provider, model and credential."""
    api_key = getattr(provider, "api_key", "") or ""
    material = f"{provider_name}:{model_id}:{api_key}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{CACHE_NAMESPACE}:{digest}"


def _is_valid_record(record: Any, provider_name: str, model_id: str) -> bool:
    return (
        isinstance(record, dict)
        and record.get("provider") == provider_name
        and record.get("model") == model_id
        and record.get("status") in STATUS_LABELS
        and record.get("availability") == label_for(record.get("status"))
        and isinstance(record.get("message"), str)
    )


def read_cached_result(provider_name: str, model_id: str, provider: Any = None):
    """Return a previously stored check result, or ``None``.

    Stale/unrecognised payloads are evicted rather than returned so a record
    from an older vocabulary can never be rendered as a current verdict.
    """
    key = cache_key(provider_name, model_id, provider)
    record = cache.get(key)
    if record is None:
        return None
    if not _is_valid_record(record, provider_name, model_id):
        cache.delete(key)
        return None
    return dict(record)


def store_result(
    provider_name: str, model_id: str, result: Dict[str, Any], provider: Any = None
) -> None:
    """Cache a check result with an outcome-appropriate TTL."""
    ttl = SUCCESS_TTL if result.get("status") == "available" else FAILURE_TTL
    cache.set(cache_key(provider_name, model_id, provider), result, timeout=ttl)


def check_model(provider: Any, provider_name: str, model_id: str) -> Dict[str, Any]:
    """Run exactly one minimal generation against ``provider``/``model_id``.

    Never raises: provider failures are classified into the availability
    vocabulary so the caller can always render a result.
    """
    try:
        reply = provider.generate_chat_response(
            messages=[{"role": "user", "content": PROBE_MESSAGE}],
            system_instruction=PROBE_SYSTEM_INSTRUCTION,
            timeout=PROBE_TIMEOUT_SECONDS,
            model_name=model_id,
            max_output_tokens=PROBE_MAX_OUTPUT_TOKENS,
        )
        if not isinstance(reply, str) or not reply.strip():
            raise AIProviderError(
                "The provider returned no generated text.", provider=provider_name
            )
        return {
            "status": "available",
            "availability": label_for("available"),
            "provider": provider_name,
            "model": model_id,
            "http_status": 200,
            "message": "A minimal generation request succeeded.",
        }
    except Exception as exc:  # noqa: BLE001 - deliberately classified, never re-raised
        result = classify_provider_error(exc)
        result.update({"provider": provider_name, "model": model_id})
        logger.info(
            "Model availability check failed (provider=%s, status=%s, error=%s).",
            provider_name,
            result["status"],
            type(exc).__name__,
        )
        return result


def unavailable_baseline(provider_name: str, model_id: str) -> Tuple[str, str, str]:
    """Baseline status for a model whose provider credentials are unusable."""
    return (
        "unknown",
        label_for("unknown"),
        "Availability has not been checked.",
    )
