import json
import logging
from typing import List, Dict

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods

from .services import availability, get_ai_provider, get_ai_status, get_available_models
from .services.base import AIProviderError
from .services.model_config import (
    get_model_configuration,
    get_registry,
    resolve_configuration,
)
from .services.job_search import search_jobs
from .ratelimit import consume_daily_request, get_daily_limit, get_remaining_requests

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = (
    "You are the Sarkari Result AI Assistant, a helpful, polite, and knowledgeable guide "
    "for candidates preparing for Indian Government examinations and recruitments.\n\n"
    "YOUR RESPONSIBILITIES:\n"
    "1. Answer queries regarding government exams (UPSC, SSC, Railways/RRB, Banking/IBPS/SBI, "
    "State PSCs, Teaching/TET, Defence/NDA/CDS, Police exams).\n"
    "2. Explain exam syllabus, exam pattern, general eligibility concepts (qualifications, "
    "age calculation rules, category reservations).\n"
    "3. Offer structured preparation tips, study timetables, and subject-wise guidance.\n"
    "4. Explain how to navigate the Sarkari Result portal (finding Latest Jobs, Admit Cards, "
    "Results, Answer Keys, and Syllabus).\n\n"
    "STRICT GROUND RULES:\n"
    "- ACCURACY: NEVER invent, guess, or hallucinate official notifications, application deadlines, "
    "application fees, vacancy counts, cutoffs, or unofficial links. If information cannot be verified, "
    "explicitly state so and advise checking the official commission or department portal.\n"
    "- PRIVACY & SAFETY: NEVER ask visitors for passwords, OTPs, Aadhaar numbers, roll numbers, "
    "or payment details. If a user provides sensitive data, caution them not to share private information.\n"
    "- TONE: Keep responses clear, helpful, supportive, and well-structured with bullet points."
)

MAX_MESSAGE_LENGTH = 1000
MAX_HISTORY_ITEMS = 12


def _login_url() -> str:
    try:
        return reverse("accounts:login")
    except Exception:
        return "/accounts/login/"


def _auth_required_response() -> JsonResponse:
    """Return an HTTP 401 JSON response for unauthenticated API clients."""
    return JsonResponse(
        {
            "status": "error",
            "code": "authentication_required",
            "error": "Please log in to use the AI assistant.",
            "login_url": _login_url(),
        },
        status=401,
    )


def _daily_limit_exceeded_response() -> JsonResponse:
    """Return an HTTP 429 JSON response when the daily limit is reached."""
    return JsonResponse(
        {
            "status": "error",
            "code": "daily_limit_reached",
            "error": (
                f"You have reached your daily limit of {get_daily_limit()} AI requests. "
                "Please try again tomorrow."
            ),
            "daily_limit": get_daily_limit(),
            "remaining_requests": 0,
        },
        status=429,
    )


def _check_request_is_authenticated(request):
    """Return None if authenticated, otherwise a 401 JsonResponse."""
    if not request.user.is_authenticated:
        return _auth_required_response()
    return None


@require_POST
def chat_api_view(request):
    """
    Secure Django Chatbot Endpoint: /api/ai/chat/
    - Requires an authenticated user (HTTP 401 otherwise).
    - Validates message type, maximum length, conversation history.
    - CSRF protection enforced.
    - Per-user daily request limit (HTTP 429 when exceeded).
    - Gemini provider.
    - Safe error handling (never exposes secrets or stack traces).
    """
    auth_error = _check_request_is_authenticated(request)
    if auth_error is not None:
        return auth_error

    # Parse JSON payload
    try:
        body = json.loads(request.body.decode("utf-8") if request.body else "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"status": "error", "code": "invalid_json", "error": "Invalid JSON payload in request."},
            status=400,
        )
    if not isinstance(body, dict):
        return JsonResponse(
            {"status": "error", "code": "invalid_payload", "error": "The request payload must be a JSON object."},
            status=400,
        )

    user_message = body.get("message")
    if not isinstance(user_message, str) or not user_message.strip():
        return JsonResponse(
            {"status": "error", "code": "empty_message", "error": "Please provide a non-empty message."},
            status=400,
        )

    requested_model = body.get("model")
    requested_provider = body.get("provider")
    if requested_model is not None and (
        not isinstance(requested_model, str)
        or not requested_model.isascii()
        or len(requested_model) > 150
    ):
        return JsonResponse(
            {"status": "error", "code": "invalid_model", "error": "Please select a supported AI model."},
            status=400,
        )
    if requested_provider is not None and (
        not isinstance(requested_provider, str)
        or requested_provider.strip().lower() not in ("gemini", "openai", "openrouter", "grok")
    ):
        return JsonResponse(
            {"status": "error", "code": "invalid_provider", "error": "Please select a supported AI provider."},
            status=400,
        )
    if (requested_model is None) != (requested_provider is None):
        return JsonResponse(
            {"status": "error", "code": "invalid_model_selection", "error": "A provider and model must be selected together."},
            status=400,
        )

    user_message = user_message.strip()
    if len(user_message) > MAX_MESSAGE_LENGTH:
        return JsonResponse(
            {
                "status": "error",
                "code": "message_too_long",
                "error": f"Message exceeds maximum allowed length of {MAX_MESSAGE_LENGTH} characters.",
            },
            status=400,
        )

    # Validate conversation history
    raw_history = body.get("history", [])
    if not isinstance(raw_history, list):
        return JsonResponse(
            {"status": "error", "code": "invalid_history", "error": "History must be a list of message objects."},
            status=400,
        )

    validated_history: List[Dict[str, str]] = []
    # Truncate to most recent turns if history is too long
    sliced_history = raw_history[-MAX_HISTORY_ITEMS:]
    for item in sliced_history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "model", "assistant") and isinstance(content, str) and content.strip():
            validated_history.append({
                "role": "model" if role == "assistant" else role,
                "content": content.strip()[:MAX_MESSAGE_LENGTH],
            })

    # Append current message to conversation turns
    validated_history.append({"role": "user", "content": user_message})

    # Check if AI feature is globally enabled (no quota consumed when disabled/unconfigured)
    is_enabled = getattr(settings, "AI_ENABLED", False)
    if not is_enabled:
        return JsonResponse(
            {
                "status": "disabled",
                "reply": (
                    "AI Assistant is currently turned off in site configuration. "
                    "To enable it, set AI_ENABLED=\"True\" in your .env file after configuring the selected AI provider."
                ),
            },
            status=200,
        )

    selected_provider_name = (
        requested_provider.strip().lower()
        if requested_provider is not None
        else str(getattr(settings, "AI_PROVIDER", "gemini")).strip().lower()
    )

    # Resolve the exact account/model from the server-side registry. The
    # registry id is authoritative because it distinguishes several accounts
    # that legitimately share one model id; provider+model is still accepted for
    # direct API clients. An unknown selection is rejected outright — it never
    # falls back to a different account or model.
    requested_config_id = body.get("config_id")
    if requested_config_id is not None and (
        not isinstance(requested_config_id, str) or len(requested_config_id) > 200
    ):
        return JsonResponse(
            {
                "status": "error",
                "code": "invalid_model",
                "error": "Please select a supported AI model.",
            },
            status=400,
        )

    if requested_config_id is not None:
        configuration = resolve_configuration(None, config_id=requested_config_id)
    elif requested_model is not None:
        configuration = resolve_configuration(selected_provider_name, requested_model)
    else:
        configuration = None

    if configuration is not None:
        selected_provider_name = configuration["provider"]
        selected_model = configuration["model"]
        provider = get_ai_provider(
            configuration["provider"],
            api_key=configuration["api_key"],
            model_name=configuration["model"],
        )
    elif requested_model is not None or requested_config_id is not None:
        return JsonResponse(
            {
                "status": "error",
                "code": "invalid_model",
                "error": "That provider/model combination is not in the current server configuration.",
            },
            status=400,
        )
    else:
        # No explicit selection: keep using the configured default provider.
        provider = get_ai_provider(selected_provider_name)
        configured_model = getattr(provider, "model_name", "")
        selected_model = configured_model if isinstance(configured_model, str) else ""

    is_ready, config_msg = provider.is_configured()
    if not is_ready:
        return JsonResponse(
            {
                "status": "unconfigured",
                "reply": config_msg,
            },
            status=200,
        )

    # Consume one daily request (atomic, row-locked). A provider failure
    # still counts because an AI attempt was consumed.
    allowed, remaining = consume_daily_request(request.user)
    if not allowed:
        return _daily_limit_exceeded_response()

    # Request completion from the exact selected provider/model. There is no
    # fallback: a failure is reported against what the user actually chose.
    try:
        reply = provider.generate_chat_response(
            messages=validated_history,
            system_instruction=SYSTEM_INSTRUCTION,
            timeout=15,
            model_name=selected_model,
        )
        if not isinstance(reply, str) or not reply.strip():
            logger.warning("Chat provider returned an empty response.")
            raise AIProviderError(
                "The provider returned no generated text.",
                provider=selected_provider_name,
            )
        return JsonResponse(
            {
                "status": "success",
                "reply": reply.strip(),
                "provider": selected_provider_name,
                "model": selected_model,
                "daily_limit": get_daily_limit(),
                "remaining_requests": remaining,
            }
        )
    except Exception as exc:
        classified = availability.classify_provider_error(exc)
        logger.warning(
            "Chat generation failed (provider=%s, model=%s, category=%s, error=%s).",
            selected_provider_name,
            selected_model,
            classified["status"],
            type(exc).__name__,
        )
        return JsonResponse(
            {
                "status": "error",
                "code": "provider_error",
                "category": classified["status"],
                "availability": classified["availability"],
                "provider": selected_provider_name,
                "model": selected_model,
                "http_status": classified["http_status"],
                "error": (
                    f"{classified['availability']} — {classified['message']} "
                    "Try again, or pick another configured model."
                ),
                "daily_limit": get_daily_limit(),
                "remaining_requests": remaining,
            },
            status=503,
        )


@require_http_methods(["GET", "POST"])
def job_search_api_view(request):
    """
    Smart Jobs Search Endpoint: /api/ai/jobs/
    - Requires an authenticated user (HTTP 401 otherwise).
    - Interprets natural language queries into validated search filters.
    - Queries verified database records using standard Django ORM.
    - Per-user daily request limit (HTTP 429 when exceeded).
    - Never generates SQL or mock/fabricated job records.
    """
    auth_error = _check_request_is_authenticated(request)
    if auth_error is not None:
        return auth_error

    query = ""
    page = 1
    limit = 10

    if request.method == "POST":
        try:
            body = json.loads(request.body.decode("utf-8") if request.body else "{}")
            if not isinstance(body, dict):
                return JsonResponse(
                    {"status": "error", "code": "invalid_payload", "error": "The request payload must be a JSON object."},
                    status=400,
                )
            raw_query = body.get("query", body.get("q", ""))
            if not isinstance(raw_query, str):
                return JsonResponse(
                    {"status": "error", "code": "invalid_payload", "error": "Search query must be text."},
                    status=400,
                )
            query = raw_query.strip()
            page = int(body.get("page", 1))
            limit = int(body.get("limit", 10))
        except (json.JSONDecodeError, ValueError):
            return JsonResponse(
                {"status": "error", "code": "invalid_payload", "error": "Invalid request payload."},
                status=400,
            )
    else:
        query = request.GET.get("q", "").strip()
        try:
            page = int(request.GET.get("page", 1))
            limit = int(request.GET.get("limit", 10))
        except ValueError:
            page = 1
            limit = 10

    # Consume one daily request (the job-query parser may invoke the AI
    # provider; even the heuristic fallback is part of the AI assistant).
    allowed, remaining = consume_daily_request(request.user)
    if not allowed:
        return _daily_limit_exceeded_response()

    results, total, filters = search_jobs(query=query, page=page, limit=limit)

    return JsonResponse(
        {
            "status": "success",
            "query": query,
            "filters": filters,
            "page": page,
            "limit": limit,
            "total": total,
            "results": results,
            "daily_limit": get_daily_limit(),
            "remaining_requests": remaining,
            "message": (
                f"Found {total} verified job{'s' if total != 1 else ''}."
                if total > 0
                else "No matching verified jobs found in the database. Please try different keywords or qualifications."
            ),
        }
    )


def ai_status_api_view(request):
    """
    Status endpoint for checking if AI is enabled and configured,
    without leaking keys or internal details.

    Requires authentication (the AI assistant is a logged-in feature).
    Also reports the user's remaining daily requests.
    """
    auth_error = _check_request_is_authenticated(request)
    if auth_error is not None:
        return auth_error

    status = get_ai_status()
    status["daily_limit"] = get_daily_limit()
    status["remaining_requests"] = get_remaining_requests(request.user)
    return JsonResponse(status)


@require_http_methods(["GET"])
def ai_models_api_view(request):
    """Return all explicitly configured provider/model pairs without upstream catalogue discovery."""
    auth_error = _check_request_is_authenticated(request)
    if auth_error is not None:
        return auth_error

    status = get_ai_status()
    model_entries = get_available_models()
    # Bind each entry to the exact registered credential so its cached verdict
    # is read back from the right account's cache slot.
    credentials = {entry["id"]: entry["api_key"] for entry in get_registry()}
    for model in model_entries:
        if not model["configured"]:
            continue
        provider = get_ai_provider(
            model["provider"],
            api_key=credentials.get(model["id"]),
            model_name=model["model"],
        )
        cached = availability.read_cached_result(
            model["provider"], model["model"], provider
        )
        if cached:
            model.update(cached)

    response_data = {
        "status": "success",
        "enabled": status["enabled"],
        "provider": status["provider"],
        "model": status["model"],
        "models": model_entries,
    }
    _, config_errors = get_model_configuration()
    response_data["configuration_errors"] = config_errors
    response_data["configured"] = any(model["configured"] for model in response_data["models"])
    if not response_data["models"]:
        response_data.update({"status": "empty", "message": "No models are explicitly configured."})
    return JsonResponse(response_data)


@require_POST
def ai_model_check_api_view(request):
    """Run one bounded generation request per manually checked model, caching its result."""
    auth_error = _check_request_is_authenticated(request)
    if auth_error is not None:
        return auth_error
    try:
        body = json.loads(request.body.decode("utf-8") if request.body else "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"status": "error", "error": "Invalid JSON payload."}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"status": "error", "error": "The request payload must be a JSON object."}, status=400)
    provider_name = body.get("provider")
    model_id = body.get("model")
    config_id = body.get("config_id")
    if config_id is not None:
        configuration = resolve_configuration(None, config_id=config_id)
    elif isinstance(provider_name, str) and isinstance(model_id, str):
        configuration = resolve_configuration(provider_name, model_id)
    else:
        configuration = None
    if configuration is None:
        return JsonResponse(
            {"status": "error", "code": "invalid_model", "error": "That provider/model combination is not configured."},
            status=400,
        )
    provider_name = configuration["provider"]
    model_id = configuration["model"]
    if not getattr(settings, "AI_ENABLED", False):
        return JsonResponse(
            {
                "status": "disabled",
                "availability": "AI disabled",
                "provider": provider_name,
                "model": model_id,
                "message": "AI model checks are disabled by site configuration.",
            },
            status=403,
        )

    provider = get_ai_provider(
        provider_name, api_key=configuration["api_key"], model_name=model_id
    )
    is_ready, config_message = provider.is_configured()
    if not is_ready:
        missing_key = not bool(getattr(provider, "api_key", ""))
        return JsonResponse(
            {
                "status": "missing_api_key" if missing_key else "not_configured",
                "availability": "Missing API key" if missing_key else "Not configured",
                "provider": provider_name,
                "model": model_id,
                "message": config_message,
            }
        )

    cached = availability.read_cached_result(provider_name, model_id, provider)
    if cached and cached.get("status") != "unknown":
        return JsonResponse(cached)

    lock_key = availability.cache_key(provider_name, model_id, provider) + ":running"
    if not cache.add(lock_key, True, timeout=20):
        return JsonResponse(
            {
                "status": "unknown",
                "availability": "Checking",
                "provider": provider_name,
                "model": model_id,
                "message": "A verification request for this model is already in progress.",
            },
            status=202,
        )

    try:
        result = availability.check_model(provider, provider_name, model_id)
        if result["status"] != "unknown":
            availability.store_result(provider_name, model_id, result, provider)
        return JsonResponse(result)
    finally:
        cache.delete(lock_key)
