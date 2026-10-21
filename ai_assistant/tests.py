import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from jobs.models import Job
from ai_assistant.models import AIDailyUsage
from ai_assistant.ratelimit import consume_daily_request, get_daily_limit
from ai_assistant.services import (
    UnsupportedAIProvider,
    availability,
    get_ai_provider,
    get_ai_status,
    get_available_models,
)
from ai_assistant.services.model_config import (
    blocks_from_env_occurrences,
    build_registry,
    get_configured_models,
    get_model_configuration,
    get_registry,
    parse_env_occurrences,
    resolve_configuration,
)
from ai_assistant.services.base import (
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
)
from ai_assistant.services.gemini_provider import GeminiProvider
from ai_assistant.services.grok_provider import GrokProvider
from ai_assistant.services.openrouter_provider import OpenRouterProvider
from ai_assistant.services.job_search import (
    parse_and_validate_filters,
    sanitize_filters,
    search_jobs,
)
from ai_assistant.views import (
    ai_model_check_api_view,
    ai_models_api_view,
    chat_api_view,
)


class ModelAvailabilityStatusTests(SimpleTestCase):
    def test_classifies_provider_failures_without_exposing_raw_messages(self):
        cases = (
            (AIRateLimitError("provider says 429", provider="openrouter", status_code=429), "rate_limited", "Rate limited / Quota exceeded"),
            (AIQuotaExceededError("quota exhausted; sk-secret", provider="gemini", status_code=429), "rate_limited", "Rate limited / Quota exceeded"),
            (AIAuthenticationError("key rejected", provider="gemini", status_code=401), "request_rejected", "Request rejected"),
            (AIModelNotFoundError("unsupported", provider="openrouter", status_code=404), "unsupported_model", "Unsupported model"),
            (AIProviderError("gateway", provider="gemini", status_code=504), "timeout_gateway", "Timeout / Gateway error"),
            (AIProviderError("upstream unavailable", provider="gemini", status_code=503), "provider_unavailable", "Provider unavailable"),
            (AIProviderError("invalid request", provider="grok", status_code=400), "request_rejected", "Request rejected"),
            (AINetworkError("connection failed", provider="openrouter"), "provider_unavailable", "Provider unavailable"),
        )
        for error, expected_status, expected_label in cases:
            with self.subTest(expected=expected_label):
                result = availability.classify_provider_error(error)
                self.assertEqual(result["status"], expected_status)
                self.assertEqual(result["availability"], expected_label)
                self.assertEqual(result["provider"], error.provider)
                self.assertNotIn("sk-secret", result["message"])
                self.assertNotIn("sk-secret", json.dumps(result))

    def test_http_403_is_classified_as_a_rejected_request_not_our_authentication(self):
        """Only our Django session may produce ``Authentication required``."""
        result = availability.classify_provider_error(
            AIAuthenticationError("forbidden", provider="gemini", status_code=403)
        )
        self.assertEqual(result["status"], "request_rejected")
        self.assertNotEqual(result["availability"], "Authentication required")

    def test_unknown_status_is_reserved_for_insufficient_evidence(self):
        result = availability.classify_provider_error(RuntimeError("something odd"))
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["availability"], "Unknown")
        self.assertIsNone(result["http_status"])

    def test_classification_preserves_only_safe_provider_error_metadata(self):
        error = AIProviderError(
            "request rejected",
            provider="grok",
            status_code=400,
            provider_error_code="invalid_parameter",
            provider_error_type="invalid_request_error",
        )
        result = availability.classify_provider_error(error)
        self.assertEqual(result["status"], "request_rejected")
        self.assertEqual(result["http_status"], 400)
        self.assertEqual(result["error_type"], "AIProviderError")
        self.assertEqual(result["provider_error_code"], "invalid_parameter")
        self.assertEqual(result["provider_error_type"], "invalid_request_error")

        error.provider_error_code = "key=secret-value"
        result = availability.classify_provider_error(error)
        self.assertNotIn("provider_error_code", result)

    @override_settings(
        AI_ENABLED=True,
        GEMINI_MODEL="status-check-model",
        GEMINI_MODEL_EXPLICIT=True,
    )
    def test_manual_check_success_response_matches_frontend_fields(self):
        request = RequestFactory().post(
            "/api/ai/models/check/",
            data=json.dumps({"provider": "gemini", "model": "status-check-model"}),
            content_type="application/json",
        )
        request.user = type("AuthenticatedUser", (), {"is_authenticated": True})()
        provider = MagicMock()
        provider.api_key = "test-only"
        provider.is_configured.return_value = (True, "configured")
        provider.generate_chat_response.return_value = "OK"
        cache_ops = (
            patch("ai_assistant.views.cache.get", return_value=None),
            patch("ai_assistant.views.cache.add", return_value=True),
            patch("ai_assistant.views.cache.set"),
            patch("ai_assistant.views.cache.delete"),
            patch("ai_assistant.views.get_ai_provider", return_value=provider),
        )
        with cache_ops[0], cache_ops[1], cache_ops[2], cache_ops[3], cache_ops[4]:
            response = ai_model_check_api_view(request)
        data = json.loads(response.content)
        self.assertEqual(data["availability"], "Available")
        self.assertEqual(data["status"], "available")
        self.assertEqual(data["provider"], "gemini")
        self.assertEqual(data["model"], "status-check-model")
        self.assertEqual(
            provider.generate_chat_response.call_args.kwargs["max_output_tokens"],
            16,
        )

    def test_frontend_reads_and_renders_the_backend_availability_field(self):
        script = (
            Path(__file__).parent
            / "static"
            / "ai_assistant"
            / "chat_widget.js"
        ).read_text(encoding="utf-8")
        self.assertIn("Object.assign(selectedModel, {", script)
        self.assertIn("model.availability", script)
        self.assertIn("updateSelectedModelOption(selectedModel)", script)
        self.assertIn('"Authentication required"', script)
        self.assertIn("await fetchModels();\n      if (!aiEnabled)", script)
        self.assertIn("if (!configuredModels.length)", script)
        self.assertNotIn("setSelectedModelState();\n    }", script)

    def test_frontend_uses_the_current_status_vocabulary_and_storage_version(self):
        script = (
            Path(__file__).parent
            / "static"
            / "ai_assistant"
            / "chat_widget.js"
        ).read_text(encoding="utf-8")
        # A persisted selection from an older widget version must never replay.
        self.assertIn("ai-assistant-selected-model:v4:", script)
        self.assertNotIn("ai-assistant-selected-model:v3:", script)
        # Every backend status code is recognised by the widget.
        for status in (
            "missing_api_key",
            "not_configured",
            "authentication_required",
            "rate_limited",
            "timeout_gateway",
            "request_rejected",
            "unsupported_model",
            "provider_unavailable",
        ):
            self.assertIn(f'"{status}"', script)
        # The old catch-all label must be gone.
        self.assertNotIn('label = "Unavailable"', script)

    @override_settings(
        AI_ENABLED=True,
        GEMINI_MODEL="selected-model",
        GEMINI_MODEL_EXPLICIT=True,
    )
    def test_model_check_preserves_classified_provider_failures(self):
        cases = (
            (AIRateLimitError("rate limited", provider="gemini", status_code=429), "Rate limited / Quota exceeded"),
            (AIProviderTimeoutError("timeout", provider="gemini", status_code=504), "Timeout / Gateway error"),
            (AIAuthenticationError("key rejected", provider="gemini", status_code=401), "Request rejected"),
            (RuntimeError("unclassified"), "Unknown"),
        )
        for error, expected in cases:
            with self.subTest(expected=expected):
                request = RequestFactory().post(
                    "/api/ai/models/check/",
                    data=json.dumps({"provider": "gemini", "model": "selected-model"}),
                    content_type="application/json",
                )
                request.user = type("AuthenticatedUser", (), {"is_authenticated": True})()
                provider = MagicMock()
                provider.api_key = "test-only"
                provider.is_configured.return_value = (True, "configured")
                provider.generate_chat_response.side_effect = error
                with patch("ai_assistant.views.cache.get", return_value=None), patch(
                    "ai_assistant.views.cache.add", return_value=True
                ), patch("ai_assistant.views.cache.delete"), patch(
                    "ai_assistant.views.cache.set"
                ), patch("ai_assistant.views.get_ai_provider", return_value=provider):
                    response = ai_model_check_api_view(request)
                result = json.loads(response.content)
                self.assertEqual(result["availability"], expected)
                self.assertEqual(result["provider"], "gemini")
                self.assertEqual(result["model"], "selected-model")

    @override_settings(
        AI_ENABLED=True,
        GEMINI_MODEL="selected-model",
        GEMINI_MODEL_EXPLICIT=True,
    )
    def test_model_check_returns_safe_error_type_and_short_failure_cache_ttl(self):
        request = RequestFactory().post(
            "/api/ai/models/check/",
            data=json.dumps({"provider": "gemini", "model": "selected-model"}),
            content_type="application/json",
        )
        request.user = type("AuthenticatedUser", (), {"is_authenticated": True})()
        provider = MagicMock()
        provider.api_key = "test-only"
        provider.is_configured.return_value = (True, "configured")
        provider.generate_chat_response.side_effect = AIProviderError(
            "request rejected",
            provider="gemini",
            status_code=400,
            provider_error_code="invalid_parameter",
        )
        with patch("ai_assistant.views.cache.get", return_value=None), patch(
            "ai_assistant.views.cache.add", return_value=True
        ), patch("ai_assistant.views.cache.delete"), patch(
            "ai_assistant.views.cache.set"
        ) as cache_set, patch(
            "ai_assistant.views.get_ai_provider", return_value=provider
        ):
            response = ai_model_check_api_view(request)
        result = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(result["availability"], "Request rejected")
        self.assertEqual(result["http_status"], 400)
        self.assertEqual(result["error_type"], "AIProviderError")
        self.assertEqual(result["provider_error_code"], "invalid_parameter")
        self.assertEqual(cache_set.call_args.kwargs["timeout"], 30)
        self.assertNotIn("invalid_parameter", result["message"])

    @override_settings(
        AI_ENABLED=True,
        GEMINI_MODEL="selected-model",
        GEMINI_MODEL_EXPLICIT=True,
    )
    def test_model_check_endpoint_rejects_anonymous_request_before_provider_call(self):
        request = RequestFactory().post(
            "/api/ai/models/check/",
            data=json.dumps({"provider": "gemini", "model": "selected-model"}),
            content_type="application/json",
        )
        request.user = type("AnonymousUser", (), {"is_authenticated": False})()
        with patch("ai_assistant.views.get_ai_provider") as provider_factory:
            response = ai_model_check_api_view(request)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(json.loads(response.content)["code"], "authentication_required")
        provider_factory.assert_not_called()

    @override_settings(AI_ENABLED=True)
    def test_model_list_ignores_legacy_unavailable_cache_payload(self):
        model = {
            "id": "gemini:cached-model",
            "provider": "gemini",
            "provider_label": "Gemini",
            "model": "cached-model",
            "label": "Gemini — cached-model",
            "status": "unknown",
            "availability": "Unknown",
            "message": "Availability has not been checked.",
            "configured": True,
        }
        provider = MagicMock()
        provider.api_key = "test-only"
        legacy_cache = {
            "status": "error",
            "availability": "Unavailable",
            "provider": "gemini",
            "model": "cached-model",
            "message": "Provider unavailable.",
        }
        request = RequestFactory().get("/api/ai/models/")
        request.user = type("AuthenticatedUser", (), {"is_authenticated": True})()
        with patch(
            "ai_assistant.views.get_ai_status",
            return_value={"enabled": True, "provider": "gemini", "model": "cached-model"},
        ), patch(
            "ai_assistant.views.get_available_models", return_value=[dict(model)]
        ), patch(
            "ai_assistant.views.get_ai_provider", return_value=provider
        ), patch(
            "ai_assistant.views.get_model_configuration", return_value=([dict(model)], [])
        ), patch(
            "ai_assistant.views.cache.get", return_value=legacy_cache
        ) as cache_get, patch(
            "ai_assistant.views.cache.delete"
        ) as cache_delete:
            response = ai_models_api_view(request)
        result = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(result["models"][0]["availability"], "Unknown")
        self.assertNotEqual(result["models"][0]["availability"], "Unavailable")
        self.assertIn(":v4:", cache_get.call_args.args[0])
        cache_delete.assert_called_once()

    @override_settings(
        AI_ENABLED=False,
        GEMINI_MODEL="configured-even-when-disabled",
        GEMINI_MODEL_EXPLICIT=True,
    )
    def test_model_list_keeps_configured_models_when_ai_is_disabled(self):
        request = RequestFactory().get("/api/ai/models/")
        request.user = type("AuthenticatedUser", (), {"is_authenticated": True})()
        status = {"enabled": False, "provider": "gemini", "model": "", "configured": False}
        model = {
            "id": "gemini:configured-even-when-disabled",
            "provider": "gemini",
            "provider_label": "Gemini",
            "model": "configured-even-when-disabled",
            "label": "Gemini ? configured-even-when-disabled",
            "configured": True,
            "status": "unknown",
            "availability": "Unknown",
            "message": "Availability has not been checked.",
        }
        with patch("ai_assistant.views.get_ai_status", return_value=status), patch(
            "ai_assistant.views.get_available_models", return_value=[model]
        ), patch("ai_assistant.views.get_ai_provider") as provider_factory, patch(
            "ai_assistant.views.cache.get", return_value=None
        ):
            response = ai_models_api_view(request)
        data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(data["enabled"])
        self.assertEqual(data["models"][0]["availability"], "Unknown")
        # The provider is built with the exact registered account credential and
        # model, never with a bare provider name.
        factory_args, factory_kwargs = provider_factory.call_args
        self.assertEqual(factory_args, ("gemini",))
        self.assertEqual(
            factory_kwargs["model_name"], "configured-even-when-disabled"
        )
        self.assertIn("api_key", factory_kwargs)

    def test_model_list_authentication_error_does_not_become_availability(self):
        request = RequestFactory().get("/api/ai/models/")
        request.user = type("AnonymousUser", (), {"is_authenticated": False})()
        response = ai_models_api_view(request)
        data = json.loads(response.content)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(data["code"], "authentication_required")
        self.assertNotIn("availability", data)

    @override_settings(
        AI_ENABLED=True,
        GEMINI_MODEL="gemini-a,gemini-b",
        GEMINI_MODEL_EXPLICIT=True,
        OPENROUTER_MODEL="router-a",
        OPENROUTER_MODEL_EXPLICIT=True,
        GROK_MODEL="grok-a",
        GROK_MODEL_EXPLICIT=True,
        GEMINI_API_KEY="",
        OPENROUTER_API_KEY="",
        GROK_API_KEY="",
    )
    def test_models_without_keys_remain_visible_as_missing_api_key(self):
        models = get_available_models()
        self.assertEqual(
            [(model["provider"], model["model"]) for model in models],
            [("gemini", "gemini-a"), ("gemini", "gemini-b"),
             ("openrouter", "router-a"), ("grok", "grok-a")],
        )
        self.assertTrue(all(model["availability"] == "Missing API key" for model in models))


class _FakeProvider:
    """Deterministic provider double: records calls and never touches the network."""

    def __init__(self, api_key="", reply="OK", error=None):
        self.api_key = api_key
        self.reply = reply
        self.error = error
        self.calls = []

    def generate_chat_response(
        self,
        messages,
        system_instruction=None,
        timeout=15,
        model_name=None,
        max_output_tokens=None,
    ):
        self.calls.append(
            {
                "messages": messages,
                "system_instruction": system_instruction,
                "timeout": timeout,
                "model_name": model_name,
                "max_output_tokens": max_output_tokens,
            }
        )
        if self.error is not None:
            raise self.error
        return self.reply


class AvailabilityServiceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_cache_namespace_is_versioned(self):
        self.assertIn(f":v{availability.CACHE_VERSION}", availability.CACHE_NAMESPACE)
        self.assertTrue(availability.CACHE_NAMESPACE.startswith("ai-model-status:"))

    def test_cache_key_is_provider_qualified_and_credential_bound(self):
        gemini = availability.cache_key("gemini", "same-model", _FakeProvider("key-a"))
        openrouter = availability.cache_key("openrouter", "same-model", _FakeProvider("key-a"))
        rotated = availability.cache_key("gemini", "same-model", _FakeProvider("key-b"))
        self.assertNotEqual(gemini, openrouter)
        self.assertNotEqual(gemini, rotated)
        self.assertTrue(gemini.startswith(availability.CACHE_NAMESPACE))

    def test_success_is_cached_longer_than_a_failure(self):
        provider = _FakeProvider("key-a")
        with patch("ai_assistant.services.availability.cache.set") as cache_set:
            availability.store_result("gemini", "m", {"status": "available"}, provider)
            self.assertEqual(cache_set.call_args.kwargs["timeout"], availability.SUCCESS_TTL)
            availability.store_result("gemini", "m", {"status": "rate_limited"}, provider)
            self.assertEqual(cache_set.call_args.kwargs["timeout"], availability.FAILURE_TTL)
        self.assertLess(availability.FAILURE_TTL, availability.SUCCESS_TTL)

    def test_cached_record_for_another_model_is_evicted(self):
        provider = _FakeProvider("key-a")
        availability.store_result(
            "gemini",
            "m",
            {
                "status": "available",
                "availability": "Available",
                "provider": "gemini",
                "model": "a-different-model",
                "message": "A minimal generation request succeeded.",
            },
            provider,
        )
        self.assertIsNone(availability.read_cached_result("gemini", "m", provider))

    def test_round_trip_returns_an_isolated_copy(self):
        provider = _FakeProvider("key-a")
        record = {
            "status": "available",
            "availability": "Available",
            "provider": "gemini",
            "model": "m",
            "message": "A minimal generation request succeeded.",
        }
        availability.store_result("gemini", "m", record, provider)
        cached = availability.read_cached_result("gemini", "m", provider)
        self.assertEqual(cached["status"], "available")
        cached["status"] = "tampered"
        self.assertEqual(
            availability.read_cached_result("gemini", "m", provider)["status"], "available"
        )

    def test_check_model_reports_availability_only_after_a_real_generation(self):
        provider = _FakeProvider("key-a", reply="OK")
        result = availability.check_model(provider, "gemini", "m")
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["availability"], "Available")
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["provider"], "gemini")
        self.assertEqual(result["model"], "m")
        self.assertEqual(
            provider.calls[0]["max_output_tokens"], availability.PROBE_MAX_OUTPUT_TOKENS
        )

    def test_check_model_probes_exactly_the_requested_model(self):
        provider = _FakeProvider("key-a", reply="OK")
        availability.check_model(provider, "openrouter", "vendor/model-a")
        self.assertEqual(provider.calls[0]["model_name"], "vendor/model-a")

    def test_check_model_never_raises(self):
        provider = _FakeProvider(
            "key-a",
            error=AIServerError("upstream exploded", provider="gemini", status_code=503),
        )
        result = availability.check_model(provider, "gemini", "m")
        self.assertEqual(result["status"], "provider_unavailable")
        self.assertEqual(result["availability"], "Provider unavailable")

    def test_empty_generation_is_not_reported_as_available(self):
        result = availability.check_model(_FakeProvider("key-a", reply="   "), "gemini", "m")
        self.assertEqual(result["status"], "unknown")

    def test_a_configured_model_is_not_available_until_checked(self):
        models = get_available_models()
        for model in models:
            self.assertIn(model["status"], ("unknown", "missing_api_key", "not_configured"))
            self.assertNotEqual(model["availability"], "Available")


class GrokProviderTests(SimpleTestCase):
    @override_settings(
        GROK_API_KEY="grok_test_key_1234567890",
        GROK_MODEL="grok-first,grok-second",
        GROK_MODEL_EXPLICIT=True,
        AI_MAX_OUTPUT_TOKENS=1024,
    )
    def test_grok_routes_explicit_model_and_minimal_token_limit(self):
        provider = GrokProvider()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}]
        }
        with patch("ai_assistant.services.grok_provider.requests.post", return_value=response) as post:
            reply = provider.generate_chat_response(
                [{"role": "user", "content": "Reply with OK."}],
                model_name="grok-second",
                timeout=10,
                max_output_tokens=16,
            )
        self.assertEqual(reply, "OK")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "grok-second")
        self.assertEqual(post.call_args.kwargs["json"]["max_tokens"], 16)

    @override_settings(
        GROK_API_KEY="grok_test_key_1234567890",
        GROK_MODEL="grok-one",
        GROK_MODEL_EXPLICIT=True,
    )
    def test_grok_preserves_provider_http_error_categories(self):
        cases = (
            (429, AIRateLimitError),
            (401, AIAuthenticationError),
            (404, AIModelNotFoundError),
            (504, AIServerError),
        )
        provider = GrokProvider()
        for status_code, error_type in cases:
            with self.subTest(status_code=status_code):
                response = MagicMock()
                response.status_code = status_code
                response.json.return_value = {"error": {"message": "provider error"}}
                with patch(
                    "ai_assistant.services.grok_provider.requests.post",
                    return_value=response,
                ):
                    with self.assertRaises(error_type) as context:
                        provider.generate_chat_response(
                            [{"role": "user", "content": "Test"}],
                            model_name="grok-one",
                        )
                self.assertEqual(context.exception.status_code, status_code)

    @override_settings(
        GROK_API_KEY="grok_test_key_1234567890",
        GROK_MODEL="grok-one",
        GROK_MODEL_EXPLICIT=True,
    )
    def test_grok_429_quota_evidence_is_not_reduced_to_rate_limit(self):
        response = MagicMock()
        response.status_code = 429
        response.json.return_value = {"error": {"message": "monthly quota exhausted"}}
        with patch(
            "ai_assistant.services.grok_provider.requests.post",
            return_value=response,
        ):
            with self.assertRaises(AIQuotaExceededError):
                GrokProvider().generate_chat_response(
                    [{"role": "user", "content": "Test"}],
                    model_name="grok-one",
                )

    @override_settings(
        GROK_API_KEY="grok_test_key_1234567890",
        GROK_MODEL="grok-one",
        GROK_MODEL_EXPLICIT=True,
    )
    def test_grok_classifies_model_code_from_safe_http_400_metadata(self):
        response = MagicMock()
        response.status_code = 400
        response.json.return_value = {
            "error": {
                "type": "invalid_request_error",
                "code": "model_not_found",
                "message": "The requested model is unavailable.",
            }
        }
        with patch(
            "ai_assistant.services.grok_provider.requests.post",
            return_value=response,
        ):
            with self.assertRaises(AIModelNotFoundError) as context:
                GrokProvider().generate_chat_response(
                    [{"role": "user", "content": "Test"}],
                    model_name="grok-one",
                )
        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(context.exception.provider_error_code, "model_not_found")
        self.assertEqual(context.exception.provider_error_type, "invalid_request_error")

    @override_settings(
        GROK_API_KEY="grok_test_key_1234567890",
        GROK_MODEL="grok-one",
        GROK_MODEL_EXPLICIT=True,
    )
    def test_grok_malformed_success_response_is_not_marked_available(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"choices": []}
        with patch(
            "ai_assistant.services.grok_provider.requests.post",
            return_value=response,
        ):
            with self.assertRaises(AIProviderError) as context:
                GrokProvider().generate_chat_response(
                    [{"role": "user", "content": "Test"}],
                    model_name="grok-one",
                )
        self.assertEqual(context.exception.status_code, 200)
        self.assertEqual(context.exception.provider_error_type, "malformed_response")
        result = availability.classify_provider_error(context.exception)
        self.assertEqual(result["availability"], "Unknown")
        self.assertEqual(result["http_status"], 200)

    @override_settings(
        GROK_API_KEY="grok_test_key_1234567890",
        GROK_MODEL="grok-one,grok-two",
        GROK_MODEL_EXPLICIT=True,
    )
    def test_grok_is_registered_and_supports_multiple_configured_models(self):
        provider = get_ai_provider("grok")
        self.assertIsInstance(provider, GrokProvider)
        self.assertEqual([item["id"] for item in provider.list_models()], ["grok-one", "grok-two"])
        self.assertTrue(provider.is_configured()[0])


class ConfiguredModelSettingsTests(SimpleTestCase):
    @override_settings(
        AI_ENABLED=True,
        GROK_MODEL="same-id",
        GROK_MODEL_EXPLICIT=True,
        GEMINI_MODEL="same-id",
        GEMINI_MODEL_EXPLICIT=True,
        OPENAI_MODEL_EXPLICIT=False,
        OPENROUTER_MODEL_EXPLICIT=False,
    )
    def test_duplicate_ids_across_providers_remain_provider_qualified(self):
        from ai_assistant.services.model_config import get_model_configuration

        models, errors = get_model_configuration()
        self.assertEqual(errors, [])
        self.assertEqual(
            [model["id"] for model in models],
            ["gemini:same-id", "grok:same-id"],
        )

    @override_settings(
        AI_ENABLED=True,
        GROK_MODEL="grok-selected",
        GROK_MODEL_EXPLICIT=True,
    )
    def test_chat_api_routes_grok_selection_to_grok_provider(self):
        request = RequestFactory().post(
            "/api/ai/chat/",
            data=json.dumps(
                {"message": "Hello", "provider": "grok", "model": "grok-selected"}
            ),
            content_type="application/json",
        )
        request.user = type("AuthenticatedUser", (), {"is_authenticated": True})()
        provider = MagicMock()
        provider.api_key = "test-only"
        provider.is_configured.return_value = (True, "configured")
        provider.generate_chat_response.return_value = "Routed Grok response"
        with patch("ai_assistant.views.get_ai_provider", return_value=provider) as factory, patch(
            "ai_assistant.views.cache.get", return_value=None
        ), patch("ai_assistant.views.consume_daily_request", return_value=(True, 19)):
            response = chat_api_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["provider"], "grok")
        factory_args, factory_kwargs = factory.call_args
        self.assertEqual(factory_args, ("grok",))
        self.assertEqual(factory_kwargs["model_name"], "grok-selected")
        self.assertEqual(
            provider.generate_chat_response.call_args.kwargs["model_name"],
            "grok-selected",
        )

    @override_settings(
        AI_ENABLED=True,
        GEMINI_MODEL="shared-name",
        GEMINI_MODEL_EXPLICIT=True,
        GROK_MODEL="shared-name",
        GROK_MODEL_EXPLICIT=True,
    )
    def test_chat_routes_duplicate_model_ids_by_provider(self):
        """The same model id on two providers must never fall back to the other."""
        seen = []

        def fake_factory(provider_name, **factory_kwargs):
            provider = MagicMock()
            provider.api_key = factory_kwargs.get("api_key") or "test-only"
            provider.is_configured.return_value = (True, "configured")
            provider.generate_chat_response.side_effect = lambda **kwargs: (
                seen.append((provider_name, kwargs["model_name"])) or f"{provider_name} reply"
            )
            return provider

        for provider_name in ("gemini", "grok"):
            request = RequestFactory().post(
                "/api/ai/chat/",
                data=json.dumps(
                    {"message": "Hello", "provider": provider_name, "model": "shared-name"}
                ),
                content_type="application/json",
            )
            request.user = type("AuthenticatedUser", (), {"is_authenticated": True})()
            with patch(
                "ai_assistant.views.get_ai_provider", side_effect=fake_factory
            ) as factory, patch(
                "ai_assistant.views.consume_daily_request", return_value=(True, 19)
            ):
                response = chat_api_view(request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(json.loads(response.content)["provider"], provider_name)
            factory_args, factory_kwargs = factory.call_args
            self.assertEqual(factory_args, (provider_name,))
            self.assertEqual(factory_kwargs["model_name"], "shared-name")

        self.assertEqual(seen, [("gemini", "shared-name"), ("grok", "shared-name")])

    @override_settings(
        GEMINI_MODEL="gemini-one,gemini-two,gemini-one",
        GEMINI_MODEL_EXPLICIT=True,
        OPENAI_MODEL="openai-one,openai-two",
        OPENAI_MODEL_EXPLICIT=True,
        OPENROUTER_MODEL="openrouter-one,openrouter-two",
        OPENROUTER_MODEL_EXPLICIT=True,
        GROK_MODEL="grok-one,grok-two",
        GROK_MODEL_EXPLICIT=True,
    )
    def test_provider_model_allowlists_are_read_separately_from_settings(self):
        self.assertEqual(
            get_configured_models("gemini"),
            ["gemini-one", "gemini-two"],
        )
        self.assertEqual(
            get_configured_models("openai"),
            ["openai-one", "openai-two"],
        )
        self.assertEqual(
            get_configured_models("openrouter"),
            ["openrouter-one", "openrouter-two"],
        )
        self.assertEqual(
            get_configured_models("grok"),
            ["grok-one", "grok-two"],
        )
        self.assertEqual(get_configured_models("unsupported"), [])


@override_settings(
    # Model lists are an allowlist. Baseline the suite on Gemini only so a
    # developer's real .env entries for other providers cannot change results.
    # The .env file registry is disabled here so every endpoint test is driven
    # purely by explicit settings; the file parser has its own dedicated tests.
    AI_MODEL_ENV_FILE="",
    OPENAI_MODEL_EXPLICIT=False,
    OPENROUTER_MODEL_EXPLICIT=False,
    GROK_MODEL_EXPLICIT=False,
)
class AIAssistantTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.today = timezone.now().date()

        # Create an authenticated user for the AI assistant endpoints.
        self.user = get_user_model().objects.create_user(
            username="aiuser",
            email="aiuser@example.com",
            password="testpass123",
        )
        self.client.force_login(self.user)

        # Seed sample verified jobs
        self.job_rrb = Job.objects.create(
            title="RRB Technician Recruitment 2026",
            organization="Railway Recruitment Board",
            qualification="10th Pass",
            location="All India",
            category="Railway",
            vacancies_count=9144,
            application_start_date=self.today - timedelta(days=2),
            application_end_date=self.today + timedelta(days=25),
            official_notification_url="https://indianrailways.gov.in/notice.pdf",
            application_url="https://rrbapply.gov.in",
            source_url="https://indianrailways.gov.in",
            last_verified_date=self.today,
            status="published",
            is_verified=True,
            is_expired=False,
        )

        self.job_ssc = Job.objects.create(
            title="SSC CGL Combined Graduate Level 2026",
            organization="Staff Selection Commission",
            qualification="Graduate",
            location="All India",
            category="Central",
            vacancies_count=14000,
            application_start_date=self.today - timedelta(days=1),
            application_end_date=self.today + timedelta(days=30),
            official_notification_url="https://ssc.gov.in/cgl_notice.pdf",
            application_url="https://ssc.gov.in",
            source_url="https://ssc.gov.in",
            last_verified_date=self.today,
            status="published",
            is_verified=True,
            is_expired=False,
        )

        self.job_police = Job.objects.create(
            title="UP Police Constable Recruitment",
            organization="UPPRPB",
            qualification="12th Pass",
            location="Uttar Pradesh",
            category="Police",
            vacancies_count=60244,
            application_start_date=self.today - timedelta(days=10),
            application_end_date=self.today + timedelta(days=15),
            status="published",
            is_verified=True,
            is_expired=False,
        )

        self.draft_job = Job.objects.create(
            title="Confidential Upcoming Draft Vacancy",
            organization="Secret Department",
            qualification="Graduate",
            status="draft",
        )

    # 1. AI DISABLED STATE
    @override_settings(AI_ENABLED=False)
    def test_ai_disabled_state(self):
        # When AI_ENABLED=False the view returns before ever touching the provider.
        # We patch the provider factory itself to confirm it is never invoked.
        url = reverse("ai_assistant:chat")
        with patch("ai_assistant.views.get_ai_provider") as mock_factory:
            response = self.client.post(
                url,
                data=json.dumps({"message": "Hello"}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "disabled")
        self.assertIn("AI Assistant is currently turned off", data.get("reply", ""))
        mock_factory.assert_not_called()

    # 2. MISSING API KEY
    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="",
    )
    def test_missing_api_key_detection(self):
        url = reverse("ai_assistant:chat")
        response = self.client.post(
            url,
            data=json.dumps({"message": "Tell me about SSC"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "unconfigured")
        self.assertIn("missing", data.get("reply", "").lower())

    # 3. PLACEHOLDER KEY DETECTION
    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="PASTE_YOUR_GEMINI_API_KEY_HERE",
        GEMINI_PLACEHOLDER_KEY="PASTE_YOUR_GEMINI_API_KEY_HERE",
    )
    def test_placeholder_key_detection(self):
        url = reverse("ai_assistant:chat")
        response = self.client.post(
            url,
            data=json.dumps({"message": "When is UPSC exam?"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "unconfigured")
        self.assertIn("placeholder", data.get("reply", "").lower())
        # Confirm that the placeholder or key itself is never leaked in the response
        self.assertNotIn("PASTE_YOUR_GEMINI_API_KEY_HERE", json.dumps(data))

    # 4. INVALID MESSAGES (Empty, Missing, Too Long, Invalid History)
    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
    )
    def test_invalid_messages_handling(self):
        url = reverse("ai_assistant:chat")

        # Empty message
        res1 = self.client.post(
            url,
            data=json.dumps({"message": ""}),
            content_type="application/json",
        )
        self.assertEqual(res1.status_code, 400)
        self.assertEqual(res1.json().get("code"), "empty_message")

        # Missing message key
        res2 = self.client.post(
            url,
            data=json.dumps({"history": []}),
            content_type="application/json",
        )
        self.assertEqual(res2.status_code, 400)

        # Non-string message
        res3 = self.client.post(
            url,
            data=json.dumps({"message": 12345}),
            content_type="application/json",
        )
        self.assertEqual(res3.status_code, 400)

        # Message exceeding max length
        long_msg = "A" * 1001
        res4 = self.client.post(
            url,
            data=json.dumps({"message": long_msg}),
            content_type="application/json",
        )
        self.assertEqual(res4.status_code, 400)
        self.assertEqual(res4.json().get("code"), "message_too_long")

        # Invalid history format
        res5 = self.client.post(
            url,
            data=json.dumps({"message": "Valid text", "history": "not-a-list"}),
            content_type="application/json",
        )
        self.assertEqual(res5.status_code, 400)
        self.assertEqual(res5.json().get("code"), "invalid_history")

    @override_settings(AI_ENABLED=False)
    def test_chat_rejects_non_object_json_payloads(self):
        response = self.client.post(
            reverse("ai_assistant:chat"),
            data=json.dumps(["not", "an", "object"]),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_payload")

    def test_job_search_rejects_non_object_json_payloads(self):
        response = self.client.post(
            reverse("ai_assistant:jobs_search"),
            data=json.dumps(["not", "an", "object"]),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_payload")

    def test_job_search_rejects_non_text_queries(self):
        response = self.client.post(
            reverse("ai_assistant:jobs_search"),
            data=json.dumps({"query": {"unexpected": "object"}}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_payload")

    # 5. CSRF PROTECTION
    def test_csrf_protection_on_chat_endpoint(self):
        csrf_client = Client(enforce_csrf_checks=True)
        url = reverse("ai_assistant:chat")
        # Attempt POST without CSRF cookie/header
        response = csrf_client.post(
            url,
            data=json.dumps({"message": "Hello without CSRF"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    # 6. PROVIDER FAILURES AND RATE LIMITS
    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
    )
    def test_provider_failure_returns_503_gracefully(self):
        url = reverse("ai_assistant:chat")
        provider = MagicMock()
        provider.is_configured.return_value = (True, "configured")
        provider.generate_chat_response.side_effect = RuntimeError(
            "provider unavailable"
        )
        with patch("ai_assistant.views.get_ai_provider", return_value=provider), patch(
            "ai_assistant.views.get_available_models",
            return_value=[
                {"id": "gemini-3.8-flash", "label": "Gemini Flash"},
                {"id": "gemini-3.8-pro", "label": "Gemini Pro"},
            ],
        ):
            response = self.client.post(
                url,
                data=json.dumps({"message": "What is the pattern of CDS exam?"}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 503)
            data = response.json()
            self.assertEqual(data.get("code"), "provider_error")
            # Ensure internal exception message is hidden from client
            self.assertNotIn("provider unavailable", data.get("error", ""))

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="gemini-3.8-flash,gemini-configured-pro",
        GEMINI_MODEL_EXPLICIT=True,
    )
    def test_chat_passes_selected_configured_model_to_provider(self):
        provider = MagicMock()
        provider.model_name = "gemini-3.8-flash"
        provider.is_configured.return_value = (True, "configured")
        provider.generate_chat_response.return_value = "Mocked answer"

        with patch("ai_assistant.views.get_ai_provider", return_value=provider):
            response = self.client.post(
                reverse("ai_assistant:chat"),
                data=json.dumps(
                    {"message": "Hello", "provider": "gemini", "model": "gemini-configured-pro"}
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            provider.generate_chat_response.call_args.kwargs["model_name"],
            "gemini-configured-pro",
        )
        provider.list_models.assert_not_called()

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
    )
    def test_chat_rejects_model_outside_configured_allowlist_even_if_upstream_lists_it(self):
        provider = MagicMock()
        provider.model_name = "gemini-3.8-flash"
        provider.is_configured.return_value = (True, "configured")
        provider.list_models.return_value = [
            {"id": "unlisted-model", "label": "Unlisted model"},
            *[
                {"id": f"upstream-model-{index}", "label": f"Model {index}"}
                for index in range(467)
            ],
        ]

        with patch("ai_assistant.views.get_ai_provider", return_value=provider):
            response = self.client.post(
                reverse("ai_assistant:chat"),
                data=json.dumps({"message": "Hello", "provider": "gemini", "model": "unlisted-model"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_model")
        provider.generate_chat_response.assert_not_called()
        provider.list_models.assert_not_called()

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
        AI_DAILY_REQUEST_LIMIT=2,
    )
    def test_daily_request_limit_enforced(self):
        url = reverse("ai_assistant:chat")
        provider = MagicMock()
        provider.is_configured.return_value = (True, "configured")
        provider.generate_chat_response.return_value = "Mocked answer"
        with patch("ai_assistant.views.get_ai_provider", return_value=provider):

            # Request 1 & 2 succeed
            res1 = self.client.post(url, data=json.dumps({"message": "Q1"}), content_type="application/json")
            self.assertEqual(res1.status_code, 200)
            self.assertEqual(res1.json().get("remaining_requests"), 1)

            res2 = self.client.post(url, data=json.dumps({"message": "Q2"}), content_type="application/json")
            self.assertEqual(res2.status_code, 200)
            self.assertEqual(res2.json().get("remaining_requests"), 0)

            # Request 3 should be rejected with 429
            res3 = self.client.post(url, data=json.dumps({"message": "Q3"}), content_type="application/json")
            self.assertEqual(res3.status_code, 429)
            self.assertEqual(res3.json().get("code"), "daily_limit_reached")
            self.assertEqual(res3.json().get("remaining_requests"), 0)

    # 7. JOB SEARCH FILTERING
    def test_job_search_by_qualification_and_keyword(self):
        # 10th pass search
        results, total, filters = search_jobs("10th pass railway jobs")
        self.assertEqual(total, 1)
        self.assertEqual(results[0]["id"], self.job_rrb.id)
        self.assertEqual(results[0]["qualification"], "10th Pass")

        # Graduate search
        results_grad, total_grad, _ = search_jobs("Graduate SSC vacancies")
        self.assertEqual(total_grad, 1)
        self.assertEqual(results_grad[0]["id"], self.job_ssc.id)

        # Location search
        results_loc, total_loc, _ = search_jobs("Uttar Pradesh police")
        self.assertEqual(total_loc, 1)
        self.assertEqual(results_loc[0]["id"], self.job_police.id)

    # 8. EMPTY SEARCH RESULTS (No fake jobs invented)
    def test_empty_search_results(self):
        results, total, filters = search_jobs("nonexistent exam title 99999")
        self.assertEqual(total, 0)
        self.assertEqual(len(results), 0)

        # API endpoint check
        url = reverse("ai_assistant:jobs_search")
        response = self.client.get(url, {"q": "nonexistent exam title 99999"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("total"), 0)
        self.assertEqual(len(data.get("results")), 0)
        self.assertIn("No matching verified jobs found", data.get("message"))

    # 9. INVALID AI-GENERATED FILTERS (Sanitization & SQL safety)
    def test_invalid_ai_generated_filters_sanitized(self):
        malicious_ai_filters = {
            "keyword": "railway",
            "malicious_sql": "'; DROP TABLE jobs_job; --",
            "dangerous_key": "123",
            "organization": "Railway",
            "location": "Delhi'); DROP TABLE jobs_job; --",
        }
        # Run search with override simulating arbitrary AI keys
        results, total, filters = search_jobs(
            query="railway",
            filters_override=malicious_ai_filters,
        )
        self.assertEqual(total, 1)
        self.assertEqual(results[0]["organization"], "Railway Recruitment Board")
        self.assertNotIn("location", filters)
        # Ensure database is intact and tables exist
        self.assertTrue(Job.objects.filter(id=self.job_rrb.id).exists())

    @override_settings(AI_ENABLED=True, AI_PROVIDER="gemini")
    def test_ai_generated_filters_are_whitelisted_and_bounded(self):
        mock_provider = MagicMock()
        mock_provider.is_configured.return_value = (True, "configured")
        mock_provider.parse_job_query.return_value = {
            "organization": "Railway",
            "location": "Uttar Pradesh'); DROP TABLE jobs_job;--",
            "keyword": "X" * 81,
            "unknown": "anything",
        }
        with patch(
            "ai_assistant.services.job_search.get_ai_provider",
            return_value=mock_provider,
        ):
            filters = parse_and_validate_filters("railway jobs")

        self.assertEqual(filters, {"organization": "Railway"})

    @override_settings(AI_ENABLED=True, AI_PROVIDER="gemini")
    def test_invalid_ai_search_filters_fall_back_to_real_database_search(self):
        mock_provider = MagicMock()
        mock_provider.is_configured.return_value = (True, "configured")
        mock_provider.parse_job_query.side_effect = RuntimeError(
            "invalid structured response"
        )
        with patch(
            "ai_assistant.services.job_search.get_ai_provider",
            return_value=mock_provider,
        ):
            results, total, filters = search_jobs("railway jobs")

        self.assertEqual(total, 1)
        self.assertEqual(results[0]["id"], self.job_rrb.id)
        self.assertTrue(
            Job.objects.filter(pk=results[0]["id"], status="published").exists()
        )

    # 10. ENSURING RETURNED JOBS EXIST IN DATABASE & NEVER DRAFT
    def test_ensuring_returned_jobs_exist_in_database_and_exclude_drafts(self):
        results, total, _ = search_jobs("")
        # Only verified, published jobs are visible in the public search.
        self.assertEqual(total, 3)
        returned_ids = [j["id"] for j in results]
        self.assertNotIn(self.draft_job.id, returned_ids)

        for job_dict in results:
            self.assertTrue(Job.objects.filter(id=job_dict["id"], status="published").exists())

    def test_job_search_excludes_unverified_published_jobs(self):
        unverified_job = Job.objects.create(
            title="Unverified published listing",
            organization="Example organization",
            qualification="Graduate",
            status="published",
            is_verified=False,
        )

        results, total, _filters = search_jobs("unverified")

        self.assertEqual(total, 0)
        self.assertFalse(any(job["id"] == unverified_job.pk for job in results))

    def test_job_search_returns_empty_for_very_large_page_number(self):
        results, _total, _filters = search_jobs("SSC", page=10**100)

        self.assertEqual(results, [])

    # 11. STATUS ENDPOINT DOES NOT EXPOSE SECRETS
    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="super_secret_real_key_xyz987",
        GEMINI_MODEL="gemini-3.8-flash",
        GEMINI_MODEL_EXPLICIT=True,
    )
    def test_status_endpoint_never_exposes_secrets(self):
        url = reverse("ai_assistant:status")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertNotIn("super_secret_real_key_xyz987", content)
        self.assertNotIn("secret", content.lower())
        data = response.json()
        self.assertTrue(data.get("enabled"))
        self.assertTrue(data.get("configured"))
        self.assertEqual(data.get("provider"), "gemini")
        self.assertEqual(data.get("model"), "gemini-3.8-flash")

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="gemini-3.8-flash",
        GEMINI_MODEL_EXPLICIT=True,
        OPENAI_MODEL_EXPLICIT=False,
        OPENROUTER_MODEL_EXPLICIT=False,
    )
    def test_models_endpoint_returns_explicit_configured_models_without_upstream_catalogue(self):
        status = {
            "enabled": True,
            "configured": True,
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "message": "configured",
        }
        provider = MagicMock()
        provider.is_configured.return_value = (True, "configured")
        provider.model_name = "gemini-3.8-flash"
        provider.list_models.return_value = [
            {"id": f"upstream-model-{index}", "label": f"Model {index}"}
            for index in range(467)
        ]
        with patch("ai_assistant.views.get_ai_status", return_value=status), patch(
            "ai_assistant.views.get_ai_provider", return_value=provider
        ):
            response = self.client.get(reverse("ai_assistant:models"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()["models"]],
            ["gemini:gemini-3.8-flash"],
        )
        provider.list_models.assert_not_called()

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="gemini-configured-one,gemini-newly-configured-model",
        GEMINI_MODEL_EXPLICIT=True,
    )
    def test_newly_configured_model_appears_without_upstream_catalogue_or_frontend_change(self):
        status = {
            "enabled": True,
            "configured": True,
            "provider": "gemini",
            "model": "gemini-configured-one",
            "message": "configured",
        }
        provider = MagicMock()
        provider.is_configured.return_value = (True, "configured")
        provider.model_name = "gemini-configured-one"
        provider.list_models.return_value = [
            {"id": f"upstream-model-{index}", "label": f"Model {index}"}
            for index in range(467)
        ]
        with patch("ai_assistant.views.get_ai_status", return_value=status), patch(
            "ai_assistant.views.get_ai_provider", return_value=provider
        ):
            response = self.client.get(reverse("ai_assistant:models"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [model["id"] for model in response.json()["models"]],
            ["gemini:gemini-configured-one", "gemini:gemini-newly-configured-model"],
        )
        provider.list_models.assert_not_called()

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="openrouter",
        OPENROUTER_API_KEY="sk-or-v1-testkey1234567890abcdef",
        OPENROUTER_MODEL="router-configured-one,router-configured-two",
        OPENROUTER_MODEL_EXPLICIT=True,
        GEMINI_MODEL="gemini-configured-one,gemini-configured-two",
        GEMINI_MODEL_EXPLICIT=True,
        OPENAI_MODEL_EXPLICIT=False,
    )
    def test_models_endpoint_combines_provider_allowlists_separately(self):
        status = {
            "enabled": True,
            "configured": True,
            "provider": "openrouter",
            "model": "router-configured-one",
            "message": "configured",
        }
        provider = MagicMock()
        provider.is_configured.return_value = (True, "configured")
        provider.model_name = "router-configured-one"
        with patch("ai_assistant.views.get_ai_status", return_value=status), patch(
            "ai_assistant.views.get_ai_provider", return_value=provider
        ):
            response = self.client.get(reverse("ai_assistant:models"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "openrouter")
        self.assertEqual(
            [model["id"] for model in response.json()["models"]],
            [
                "gemini:gemini-configured-one",
                "gemini:gemini-configured-two",
                "openrouter:router-configured-one",
                "openrouter:router-configured-two",
            ],
        )
        self.assertIn("gemini-configured-one", response.content.decode())

    def test_models_endpoint_requires_authentication(self):
        self.client.logout()
        with patch("ai_assistant.views.get_available_models") as list_models:
            response = self.client.get(reverse("ai_assistant:models"))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "authentication_required")
        list_models.assert_not_called()

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="gemini-3.8-flash",
        GEMINI_MODEL_EXPLICIT=False,
        OPENAI_MODEL_EXPLICIT=False,
        OPENROUTER_MODEL_EXPLICIT=False,
    )
    def test_models_endpoint_reports_empty_configured_model_list(self):
        status = {
            "enabled": True,
            "configured": True,
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "message": "configured",
        }
        provider = MagicMock()
        provider.is_configured.return_value = (True, "configured")
        with patch("ai_assistant.views.get_ai_status", return_value=status), patch(
            "ai_assistant.views.get_ai_provider", return_value=provider
        ):
            response = self.client.get(reverse("ai_assistant:models"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "empty")
        self.assertEqual(response.json()["models"], [])
        provider.list_models.assert_not_called()

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="same-model",
        GEMINI_MODEL_EXPLICIT=True,
        OPENROUTER_API_KEY="",
        OPENROUTER_MODEL="same-model",
        OPENROUTER_MODEL_EXPLICIT=True,
        OPENAI_MODEL_EXPLICIT=False,
    )
    def test_duplicate_model_ids_are_kept_separate_by_provider(self):
        response = self.client.get(reverse("ai_assistant:models"))
        self.assertEqual(response.status_code, 200)
        models = response.json()["models"]
        self.assertEqual(
            [model["id"] for model in models],
            ["gemini:same-model", "openrouter:same-model"],
        )
        # The duplicate id is a distinct entry, and because OpenRouter has no
        # key it reports the accurate "Missing API key" status instead of
        # disappearing or being folded into the Gemini entry.
        self.assertEqual(models[1]["status"], "missing_api_key")
        self.assertEqual(models[1]["availability"], "Missing API key")

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="unavailable-model",
        GEMINI_MODEL_EXPLICIT=True,
        OPENAI_MODEL_EXPLICIT=False,
        OPENROUTER_MODEL_EXPLICIT=False,
    )
    def test_cached_failing_model_remains_in_model_list_with_accurate_status(self):
        cached_result = {
            "status": "unsupported_model",
            "availability": "Unsupported model",
            "provider": "gemini",
            "model": "unavailable-model",
            "message": "The provider reported that this model id is not supported.",
        }
        with patch("ai_assistant.views.cache.get", return_value=cached_result):
            response = self.client.get(reverse("ai_assistant:models"))
        self.assertEqual(response.status_code, 200)
        models = response.json()["models"]
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["id"], "gemini:unavailable-model")
        self.assertEqual(models[0]["status"], "unsupported_model")
        self.assertEqual(models[0]["availability"], "Unsupported model")

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="unavailable-model",
        GEMINI_MODEL_EXPLICIT=True,
        OPENAI_MODEL_EXPLICIT=False,
        OPENROUTER_MODEL_EXPLICIT=False,
    )
    def test_stale_cached_verdict_is_evicted_and_not_rendered(self):
        """A record written by an older vocabulary must never be displayed."""
        stale_result = {
            "status": "model_unavailable",
            "availability": "Model unavailable / Unsupported",
            "message": "The provider rejected this model ID.",
        }
        with patch("ai_assistant.views.cache.get", return_value=stale_result), patch(
            "ai_assistant.views.cache.delete"
        ) as cache_delete:
            response = self.client.get(reverse("ai_assistant:models"))
        self.assertEqual(response.status_code, 200)
        models = response.json()["models"]
        self.assertEqual(models[0]["status"], "unknown")
        self.assertEqual(models[0]["availability"], "Unknown")
        cache_delete.assert_called_once()

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="selected-gemini",
        GEMINI_MODEL_EXPLICIT=True,
        OPENROUTER_API_KEY="sk-or-v1-testkey1234567890abcdef",
        OPENROUTER_MODEL="selected-router",
        OPENROUTER_MODEL_EXPLICIT=True,
    )
    def test_chat_routes_to_explicitly_selected_provider_and_model(self):
        provider = MagicMock()
        provider.is_configured.return_value = (True, "configured")
        provider.generate_chat_response.return_value = "Routed answer"
        with patch(
            "ai_assistant.views.get_ai_provider", return_value=provider
        ) as factory:
            response = self.client.post(
                reverse("ai_assistant:chat"),
                data=json.dumps(
                    {
                        "message": "Hello",
                        "provider": "openrouter",
                        "model": "selected-router",
                    }
                ),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        factory_args, factory_kwargs = factory.call_args
        self.assertEqual(factory_args, ("openrouter",))
        self.assertEqual(factory_kwargs["model_name"], "selected-router")
        self.assertEqual(
            provider.generate_chat_response.call_args.kwargs["model_name"],
            "selected-router",
        )
        self.assertEqual(response.json()["provider"], "openrouter")

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="only-configured",
        GEMINI_MODEL_EXPLICIT=True,
    )
    def test_chat_rejects_unconfigured_provider_model_pair(self):
        response = self.client.post(
            reverse("ai_assistant:chat"),
            data=json.dumps(
                {"message": "Hello", "provider": "openrouter", "model": "only-configured"}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_model")

    @override_settings(
        AI_ENABLED=True,
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="checkable-model",
        GEMINI_MODEL_EXPLICIT=True,
    )
    def test_manual_model_check_uses_one_minimal_generation(self):
        provider = MagicMock()
        provider.is_configured.return_value = (True, "configured")
        provider.generate_chat_response.return_value = "OK"
        with patch("ai_assistant.views.get_ai_provider", return_value=provider):
            response = self.client.post(
                reverse("ai_assistant:models_check"),
                data=json.dumps({"provider": "gemini", "model": "checkable-model"}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "available")
        self.assertEqual(
            provider.generate_chat_response.call_args.kwargs["max_output_tokens"], 16
        )

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="gemini-3.8-flash",
    )
    # 12. AI_ENABLED DISABLED SHOWS CORRECT MESSAGE
    @override_settings(
        AI_ENABLED=False,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="PASTE_YOUR_GEMINI_API_KEY_HERE",
        GEMINI_PLACEHOLDER_KEY="PASTE_YOUR_GEMINI_API_KEY_HERE",
    )
    def test_ai_disabled_shows_correct_message(self):
        """Test that when AI_ENABLED=False, status endpoint shows disabled message."""
        url = reverse("ai_assistant:status")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data.get("enabled"))
        self.assertIn("disabled", data.get("message", "").lower())
        self.assertIn("AI_ENABLED=False", data.get("message", ""))

    # 13. PLACEHOLDER KEY DETECTED EVEN WHEN AI_ENABLED
    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="PASTE_YOUR_GEMINI_API_KEY_HERE",
        GEMINI_PLACEHOLDER_KEY="PASTE_YOUR_GEMINI_API_KEY_HERE",
    )
    def test_placeholder_key_detected_when_enabled(self):
        """Test that placeholder key is detected even if AI_ENABLED=True."""
        url = reverse("ai_assistant:status")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("enabled"))  # AI_ENABLED is True
        self.assertFalse(data.get("configured"))  # But not configured due to placeholder
        self.assertIn("placeholder", data.get("message", "").lower())

    # 14. ENV LOADING FROM CORRECT DIRECTORY
    def test_env_loaded_from_project_root(self):
        """Test that .env is loaded from the correct project-root directory."""
        from pathlib import Path
        from django.conf import settings
        
        # Verify BASE_DIR points to project root
        base_dir = getattr(settings, "BASE_DIR", None)
        self.assertIsNotNone(base_dir)
        
        # In test environments, .env may not exist - check for .env.example instead
        env_path = base_dir / ".env"
        env_example_path = base_dir / ".env.example"
        
        # At least one of these should exist
        self.assertTrue(
            env_path.exists() or env_example_path.exists(),
            f"Either .env or .env.example should exist at {base_dir}"
        )
        
        # Verify settings are being loaded from environment
        # (This test assumes .env.example values are being used as defaults)
        self.assertIsNotNone(getattr(settings, "AI_PROVIDER", None))
        self.assertIsNotNone(getattr(settings, "GEMINI_MODEL", None))

    # 15. STATUS ENDPOINT DISTINGUISHES DISABLED VS UNCONFIGURED
    @override_settings(
        AI_ENABLED=False,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
    )
    def test_status_distinguishes_disabled_from_unconfigured(self):
        """Test that disabled (AI_ENABLED=False) is distinct from unconfigured (missing key)."""
        url = reverse("ai_assistant:status")
        response = self.client.get(url)
        data = response.json()
        
        # When AI_ENABLED=False, it should show as disabled regardless of key
        self.assertFalse(data.get("enabled"))
        self.assertIn("disabled", data.get("message", "").lower())
        self.assertNotIn("missing", data.get("message", "").lower())

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="secret_gemini_key_0123456789",
    )
    def test_chat_response_never_echoes_api_key(self):
        # Skip this test on Python 3.13 due to google-genai compatibility issues
        import sys
        if sys.version_info >= (3, 13):
            self.skipTest("google-genai has compatibility issues with Python 3.13")
        
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(
            text="Sensitive: secret_gemini_key_0123456789",
            candidates=[],
        )
        # Patch where GeminiProvider._get_client() constructs the SDK client
        import google.genai as _genai_module
        with patch.object(_genai_module, "Client", return_value=mock_client):
            response = self.client.post(
                reverse("ai_assistant:chat"),
                data=json.dumps({"message": "Hello"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "secret_gemini_key_0123456789",
            response.content.decode("utf-8"),
        )
        self.assertIn("[redacted]", response.json()["reply"])

    @override_settings(AI_ENABLED=True, AI_PROVIDER="gemini")
    def test_chat_timeout_returns_clear_safe_error(self):
        provider = MagicMock()
        provider.is_configured.return_value = (True, "configured")
        provider.generate_chat_response.side_effect = AIProviderTimeoutError(
            "The AI assistant request timed out. Please try again."
        )
        with patch("ai_assistant.views.get_ai_provider", return_value=provider):
            response = self.client.post(
                reverse("ai_assistant:chat"),
                data=json.dumps({"message": "Hello"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["code"], "provider_error")
        self.assertEqual(payload["category"], "timeout_gateway")
        self.assertEqual(payload["availability"], "Timeout / Gateway error")
        self.assertEqual(payload["provider"], "gemini")
        self.assertIn("Timeout / Gateway error", payload["error"])
        self.assertNotIn("The AI assistant request timed out", payload["error"])

    # ---------------- Authentication & Rate Limiting ----------------

    def test_anonymous_access_returns_401(self):
        """Anonymous users must be rejected with 401 on every AI endpoint."""
        anon = Client()  # not logged in
        for url_name in ("ai_assistant:chat", "ai_assistant:jobs_search", "ai_assistant:status"):
            url = reverse(url_name)
            method = "get" if url_name == "ai_assistant:status" else "post"
            if method == "post":
                resp = anon.post(
                    url,
                    data=json.dumps({"message": "hi"}),
                    content_type="application/json",
                )
            else:
                resp = anon.get(url)
            self.assertEqual(
                resp.status_code,
                401,
                f"Anonymous access to {url_name} should return 401, got {resp.status_code}",
            )
            self.assertEqual(resp.json().get("code"), "authentication_required")

    def test_anonymous_401_response_points_to_real_login_url(self):
        """The 401 payload must contain Django's actual named login URL."""
        anon = Client()
        resp = anon.post(
            reverse("ai_assistant:chat"),
            data=json.dumps({"message": "hi"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json().get("login_url"), reverse("accounts:login"))

    def test_anonymous_jobs_get_request_returns_401(self):
        """GET on the job-search endpoint must also be rejected anonymously."""
        anon = Client()
        resp = anon.get(reverse("ai_assistant:jobs_search"), {"q": "railway"})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json().get("code"), "authentication_required")

    def test_anonymous_request_cannot_consume_quota_via_forged_identity(self):
        """A client-supplied username must never be trusted by the backend."""
        anon = Client()
        anon.post(
            reverse("ai_assistant:chat"),
            data=json.dumps({"message": "hi", "username": self.user.username}),
            content_type="application/json",
        )
        self.assertFalse(AIDailyUsage.objects.filter(user=self.user).exists())

    def test_anonymous_status_endpoint_reveals_no_quota_information(self):
        """The anonymous 401 response must not contain personal usage data."""
        anon = Client()
        resp = anon.get(reverse("ai_assistant:status"))
        self.assertEqual(resp.status_code, 401)
        body = resp.json()
        self.assertNotIn("remaining_requests", body)
        self.assertNotIn("daily_limit", body)

    def test_anonymous_requests_are_not_counted(self):
        """Rejected anonymous requests must never consume the daily quota."""
        anon = Client()
        for endpoint in ("ai_assistant:chat", "ai_assistant:jobs_search"):
            anon.post(
                reverse(endpoint),
                data=json.dumps({"message": "hi", "query": "railway"}),
                content_type="application/json",
            )
        self.assertFalse(AIDailyUsage.objects.filter(user=self.user).exists())

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
    )
    def test_authenticated_chat_response_includes_remaining_requests(self):
        provider = MagicMock()
        provider.is_configured.return_value = (True, "configured")
        provider.generate_chat_response.return_value = "Hi!"
        with patch("ai_assistant.views.get_ai_provider", return_value=provider):
            resp = self.client.post(
                reverse("ai_assistant:chat"),
                data=json.dumps({"message": "Hello"}),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("remaining_requests", data)
        self.assertIn("daily_limit", data)
        self.assertEqual(data["daily_limit"], get_daily_limit())
        self.assertEqual(data["remaining_requests"], get_daily_limit() - 1)

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
        AI_DAILY_REQUEST_LIMIT=20,
    )
    def test_twenty_requests_allowed_twenty_first_rejected(self):
        """Exactly 20 requests succeed; the 21st must return 429."""
        provider = MagicMock()
        provider.is_configured.return_value = (True, "configured")
        provider.generate_chat_response.return_value = "ok"
        url = reverse("ai_assistant:chat")
        with patch("ai_assistant.views.get_ai_provider", return_value=provider):
            for i in range(20):
                resp = self.client.post(
                    url,
                    data=json.dumps({"message": f"Q{i}"}),
                    content_type="application/json",
                )
                self.assertEqual(resp.status_code, 200, f"Request {i + 1} should succeed")
            twenty_first = self.client.post(
                url,
                data=json.dumps({"message": "Q21"}),
                content_type="application/json",
            )
        self.assertEqual(twenty_first.status_code, 429)
        self.assertEqual(twenty_first.json().get("code"), "daily_limit_reached")

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
    )
    def test_anonymous_request_never_invokes_provider(self):
        """The Gemini provider must never be reached by an anonymous request."""
        anon = Client()
        provider = MagicMock()
        provider.is_configured.return_value = (True, "configured")
        provider.generate_chat_response.return_value = "should never happen"
        with patch("ai_assistant.views.get_ai_provider", return_value=provider) as mock_factory:
            resp = anon.post(
                reverse("ai_assistant:chat"),
                data=json.dumps({"message": "hi"}),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 401)
        mock_factory.assert_not_called()
        provider.generate_chat_response.assert_not_called()

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
    )
    def test_job_search_fallback_uses_real_database_without_ai(self):
        """When AI is enabled, the job-search endpoint still works via its heuristic fallback."""
        provider = MagicMock()
        provider.is_configured.return_value = (True, "configured")
        provider.parse_job_query.side_effect = RuntimeError("invalid structured response")
        with patch("ai_assistant.services.job_search.get_ai_provider", return_value=provider):
            resp = self.client.post(
                reverse("ai_assistant:jobs_search"),
                data=json.dumps({"query": "railway"}),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["results"][0]["id"], self.job_rrb.id)

    @override_settings(AI_DAILY_REQUEST_LIMIT=20)
    def test_daily_limit_resets_at_midnight(self):
        """A row from yesterday must not count against today's quota."""
        yesterday = timezone.now().date() - timedelta(days=1)
        AIDailyUsage.objects.create(
            user=self.user, usage_date=yesterday, request_count=get_daily_limit()
        )
        allowed, remaining = consume_daily_request(self.user)
        self.assertTrue(allowed)
        self.assertEqual(remaining, get_daily_limit() - 1)
        self.assertEqual(AIDailyUsage.objects.filter(user=self.user, usage_date=yesterday).count(), 1)
        self.assertTrue(AIDailyUsage.objects.filter(user=self.user, usage_date=timezone.now().date()).exists())


@override_settings(AI_DAILY_REQUEST_LIMIT=10)
class AIDailyUsageConcurrencyTests(TransactionTestCase):
    """Verify atomicity of the daily counter under concurrent requests."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="concurrency_user",
            email="concurrency@example.com",
            password="testpass123",
        )

    def test_concurrent_requests_do_not_exceed_limit(self):
        """Concurrent consume calls must never let the counter exceed the limit."""
        limit = get_daily_limit()
        num_threads = limit + 15  # fire more than the limit concurrently

        def _worker(_i):
            # SQLite serializes writers at the table level; transient
            # "database is locked" errors are expected under contention and
            # are retried (as a real app/DB driver would do).
            for attempt in range(20):
                try:
                    return consume_daily_request(self.user)
                except OperationalError:
                    time.sleep(0.02 * (attempt + 1))
            # If we exhausted retries, treat as not allowed.
            return (False, 0)

        with ThreadPoolExecutor(max_workers=num_threads) as ex:
            results = list(ex.map(_worker, range(num_threads)))

        allowed_count = sum(1 for allowed, _ in results if allowed)
        row = AIDailyUsage.objects.get(user=self.user, usage_date=timezone.now().date())
        self.assertEqual(allowed_count, limit)
        self.assertEqual(row.request_count, limit)


class GeminiProviderTests(TestCase):
    @override_settings(
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="gemini-3.8-flash",
    )
    def test_factory_selects_gemini_provider(self):
        self.assertIsInstance(get_ai_provider(), GeminiProvider)

    @override_settings(AI_PROVIDER="not-a-provider")
    def test_factory_rejects_unknown_provider_without_fallback(self):
        provider = get_ai_provider()

        self.assertIsInstance(provider, UnsupportedAIProvider)
        self.assertFalse(provider.is_configured()[0])
        self.assertIn("not supported", provider.is_configured()[1])

    @override_settings(
        GEMINI_API_KEY="",
        GEMINI_MODEL="gemini-3.8-flash",
    )
    def test_missing_key_is_reported_without_network_call(self):
        provider = GeminiProvider()

        self.assertFalse(provider.is_configured()[0])
        self.assertIn("missing", provider.is_configured()[1].lower())

    @override_settings(
        GEMINI_API_KEY="PASTE_YOUR_GEMINI_API_KEY_HERE",
        GEMINI_MODEL="gemini-3.8-flash",
    )
    def test_placeholder_key_is_reported_without_network_call(self):
        provider = GeminiProvider()

        self.assertFalse(provider.is_configured()[0])
        self.assertIn("placeholder", provider.is_configured()[1].lower())

    @override_settings(
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="bad model name",
    )
    def test_invalid_model_name_is_reported_without_exposing_credentials(self):
        provider = GeminiProvider()

        configured, message = provider.is_configured()

        self.assertFalse(configured)
        self.assertIn("model configuration is invalid", message)
        self.assertNotIn("gemini_test_key_0123456789", message)

    @override_settings(
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="gemini-2.5-flash",
    )
    def test_missing_sdk_is_reported_as_unconfigured(self):
        provider = GeminiProvider()

        with patch("ai_assistant.services.gemini_provider.find_spec", return_value=None):
            configured, message = provider.is_configured()

        self.assertFalse(configured)
        self.assertIn("SDK is unavailable", message)

    @override_settings(
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="gemini-3.8-flash",
    )
    def test_gemini_model_discovery_only_returns_generate_content_models(self):
        provider = GeminiProvider()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "models": [
                {
                    "name": "models/gemini-3.8-flash",
                    "displayName": "Gemini Flash",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/text-embedding-004",
                    "displayName": "Embedding",
                    "supportedGenerationMethods": ["embedContent"],
                },
            ]
        }

        with patch(
            "ai_assistant.services.gemini_provider.requests.get",
            return_value=response,
        ) as get:
            models = provider.list_models(timeout=4)

        self.assertEqual(
            models,
            [{"id": "gemini-3.8-flash", "label": "Gemini Flash"}],
        )
        self.assertEqual(get.call_args.kwargs["timeout"], 4)
        self.assertNotIn("gemini_test_key_0123456789", str(models))

    @override_settings(
        AI_PROVIDER=None,
        GEMINI_API_KEY="secret_test_key_0123456789",
    )
    def test_non_string_provider_setting_is_handled_safely(self):
        self.assertIsInstance(get_ai_provider(), UnsupportedAIProvider)
        status = get_ai_status()

        self.assertEqual(status["provider"], "unsupported")
        self.assertFalse(status["configured"])
        self.assertNotIn("secret_test_key_0123456789", str(status))

    @override_settings(
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="gemini-3.8-flash",
    )
    def test_chat_timeout_is_passed_to_sdk_in_milliseconds(self):
        # Skip this test on Python 3.13 due to google-genai compatibility issues
        import sys
        if sys.version_info >= (3, 13):
            self.skipTest("google-genai has compatibility issues with Python 3.13")
        
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(
            text="Mocked Gemini response",
            candidates=[],
        )
        provider = GeminiProvider()

        import google.genai as _genai_module
        with patch.object(_genai_module, "Client", return_value=mock_client):
            reply = provider.generate_chat_response(
                [{"role": "user", "content": "Hello"}],
                timeout=15,
            )

        self.assertEqual(reply, "Mocked Gemini response")
        kwargs = mock_client.models.generate_content.call_args.kwargs
        self.assertEqual(kwargs["model"], "gemini-3.8-flash")
        self.assertEqual(kwargs["config"].http_options.timeout, 15000)

    @override_settings(
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="gemini-3.8-flash",
    )
    def test_sdk_timeout_exception_becomes_safe_provider_timeout(self):
        # Skip this test on Python 3.13 due to google-genai compatibility issues
        import sys
        if sys.version_info >= (3, 13):
            self.skipTest("google-genai has compatibility issues with Python 3.13")
        
        import httpx

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = httpx.ReadTimeout(
            "request contained sensitive transport details"
        )
        provider = GeminiProvider()

        import google.genai as _genai_module
        with patch.object(_genai_module, "Client", return_value=mock_client):
            with self.assertRaises(AIProviderTimeoutError) as error:
                provider.generate_chat_response(
                    [{"role": "user", "content": "Hello"}],
                    timeout=15,
                )

        self.assertEqual(
            str(error.exception),
            "The AI assistant request timed out. Please try again.",
        )
        self.assertNotIn("sensitive transport details", str(error.exception))

    @override_settings(
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="gemini-3.8-flash",
    )
    def test_empty_provider_response_is_not_reported_as_success(self):
        # Skip this test on Python 3.13 due to google-genai compatibility issues
        import sys
        if sys.version_info >= (3, 13):
            self.skipTest("google-genai has compatibility issues with Python 3.13")
        
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(
            text="",
            candidates=[],
        )

        with patch("google.genai.Client", return_value=mock_client):
            with self.assertRaisesRegex(RuntimeError, "temporarily unavailable"):
                GeminiProvider().generate_chat_response(
                    [{"role": "user", "content": "Hello"}],
                    timeout=15,
                )


class AIConfigurationCheckTests(SimpleTestCase):
    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER=None,
        GEMINI_API_KEY="secret_test_key_0123456789",
    )
    def test_check_warns_for_unsupported_provider_without_echoing_values(self):
        from ai_assistant.checks import check_ai_configuration

        warnings = check_ai_configuration(None)

        self.assertEqual([warning.id for warning in warnings], ["ai_assistant.W001"])
        self.assertNotIn("secret_test_key_0123456789", str(warnings))

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="",
        GEMINI_MODEL="invalid model",
    )
    def test_check_warns_for_missing_credentials_and_invalid_model(self):
        from ai_assistant.checks import check_ai_configuration

        warnings = check_ai_configuration(None)

        self.assertEqual(
            {warning.id for warning in warnings},
            {"ai_assistant.W002", "ai_assistant.W003"},
        )

    @override_settings(
        AI_ENABLED=False,
        AI_PROVIDER="unknown",
        GEMINI_API_KEY="",
    )
    def test_check_does_not_warn_when_ai_is_disabled(self):
        from ai_assistant.checks import check_ai_configuration

        self.assertEqual(check_ai_configuration(None), [])

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="openrouter",
        OPENROUTER_API_KEY="",
        OPENROUTER_MODEL="invalid model with spaces",
    )
    def test_check_warns_for_openrouter_missing_credentials_and_invalid_model(self):
        from ai_assistant.checks import check_ai_configuration

        warnings = check_ai_configuration(None)
        self.assertEqual(
            {warning.id for warning in warnings},
            {"ai_assistant.W008", "ai_assistant.W009"},
        )

    @override_settings(
        AI_ENABLED=True,
        AI_PROVIDER="openrouter",
        OPENROUTER_API_KEY="sk-or-v1-validformat0123456789abcdef",
        OPENROUTER_MODEL="nvidia/nemotron-3-ultra-550b-a55b-20260604",
    )
    def test_check_passes_for_valid_openrouter_configuration(self):
        from ai_assistant.checks import check_ai_configuration

        warnings = check_ai_configuration(None)
        self.assertEqual(warnings, [])


class OpenRouterProviderTests(TestCase):
    @override_settings(
        AI_PROVIDER="openrouter",
        OPENROUTER_API_KEY="sk-or-v1-testkey1234567890abcdef",
        OPENROUTER_MODEL="nvidia/nemotron-3-ultra-550b-a55b-20260604",
    )
    def test_factory_selects_openrouter_provider(self):
        provider = get_ai_provider()
        self.assertIsInstance(provider, OpenRouterProvider)
        self.assertEqual(provider.model_name, "nvidia/nemotron-3-ultra-550b-a55b-20260604")

    @override_settings(
        OPENROUTER_API_KEY="",
        OPENROUTER_MODEL="nvidia/nemotron-3-ultra-550b-a55b-20260604",
    )
    def test_missing_openrouter_key_is_reported(self):
        provider = OpenRouterProvider()
        configured, message = provider.is_configured()
        self.assertFalse(configured)
        self.assertIn("missing", message.lower())

    @override_settings(
        OPENROUTER_API_KEY="PASTE_YOUR_OPENROUTER_API_KEY_HERE",
        OPENROUTER_MODEL="nvidia/nemotron-3-ultra-550b-a55b-20260604",
    )
    def test_placeholder_openrouter_key_is_reported(self):
        provider = OpenRouterProvider()
        configured, message = provider.is_configured()
        self.assertFalse(configured)
        self.assertIn("placeholder", message.lower())

    @override_settings(
        OPENROUTER_API_KEY="short-key",
        OPENROUTER_MODEL="nvidia/nemotron-3-ultra-550b-a55b-20260604",
    )
    def test_invalid_format_openrouter_key_is_reported(self):
        provider = OpenRouterProvider()
        configured, message = provider.is_configured()
        self.assertFalse(configured)
        self.assertIn("invalid", message.lower())

    @override_settings(
        OPENROUTER_API_KEY="sk-or-v1-testkey1234567890abcdef",
        OPENROUTER_MODEL="bad model with spaces",
    )
    def test_invalid_openrouter_model_is_reported(self):
        provider = OpenRouterProvider()
        configured, message = provider.is_configured()
        self.assertFalse(configured)
        self.assertIn("invalid", message.lower())

    @override_settings(
        OPENROUTER_API_KEY="sk-or-v1-testkey1234567890abcdef",
        OPENROUTER_MODEL="nvidia/nemotron-3-ultra-550b-a55b-20260604",
    )
    def test_successful_openrouter_chat_response(self):
        provider = OpenRouterProvider()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "Hello candidate!"}}]
        }
        with patch("requests.post", return_value=mock_response):
            reply = provider.generate_chat_response([{"role": "user", "content": "Hi"}])
        self.assertEqual(reply, "Hello candidate!")

    @override_settings(
        OPENROUTER_API_KEY="sk-or-v1-testkey1234567890abcdef",
        OPENROUTER_MODEL="nvidia/nemotron-3-ultra-550b-a55b-20260604",
    )
    def test_openrouter_model_discovery_only_returns_text_output_models(self):
        provider = OpenRouterProvider()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "data": [
                {
                    "id": "provider/text-model",
                    "name": "Provider Text Model",
                    "architecture": {"output_modalities": ["text"]},
                },
                {
                    "id": "provider/image-model",
                    "name": "Provider Image Model",
                    "architecture": {"output_modalities": ["image"]},
                },
            ]
        }

        with patch(
            "ai_assistant.services.openrouter_provider.requests.get",
            return_value=response,
        ) as get:
            models = provider.list_models(timeout=4)

        self.assertEqual(
            models,
            [{"id": "provider/text-model", "label": "Provider Text Model"}],
        )
        self.assertEqual(get.call_args.kwargs["timeout"], 4)
        self.assertNotIn("sk-or-v1-testkey1234567890abcdef", str(models))

    @override_settings(
        OPENROUTER_API_KEY="sk-or-v1-secretkey0000000000",
        OPENROUTER_MODEL="nvidia/nemotron-3-ultra-550b-a55b-20260604",
    )
    def test_openrouter_response_redacts_api_key(self):
        provider = OpenRouterProvider()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "Your key is sk-or-v1-secretkey0000000000."}}]
        }
        with patch("requests.post", return_value=mock_response):
            reply = provider.generate_chat_response([{"role": "user", "content": "Hi"}])
        self.assertNotIn("sk-or-v1-secretkey0000000000", reply)
        self.assertIn("[redacted]", reply)

    @override_settings(
        OPENROUTER_API_KEY="sk-or-v1-testkey1234567890abcdef",
        OPENROUTER_MODEL="nvidia/nemotron-3-ultra-550b-a55b-20260604",
    )
    def test_openrouter_timeout_raises_provider_timeout_error(self):
        import requests
        provider = OpenRouterProvider()
        with patch("requests.post", side_effect=requests.Timeout("Request timed out")):
            with self.assertRaises(AIProviderTimeoutError):
                provider.generate_chat_response([{"role": "user", "content": "Hi"}])

    @override_settings(
        OPENROUTER_API_KEY="sk-or-v1-testkey1234567890abcdef",
        OPENROUTER_MODEL="nvidia/nemotron-3-ultra-550b-a55b-20260604",
    )
    def test_openrouter_error_classifications(self):
        provider = OpenRouterProvider()
        error_cases = [
            (401, AIAuthenticationError),
            (402, AIPaymentRequiredError),
            (404, AIModelNotFoundError),
            (429, AIRateLimitError),
            (500, AIServerError),
        ]
        for status_code, expected_exc in error_cases:
            mock_response = MagicMock()
            mock_response.status_code = status_code
            mock_response.json.return_value = {"error": {"message": f"Error {status_code}"}}
            with patch("requests.post", return_value=mock_response):
                with self.assertRaises(expected_exc):
                    provider.generate_chat_response([{"role": "user", "content": "Hi"}])

    @override_settings(
        OPENROUTER_API_KEY="sk-or-v1-testkey1234567890abcdef",
        OPENROUTER_MODEL="nvidia/nemotron-3-ultra-550b-a55b-20260604",
    )
    def test_openrouter_parse_job_query(self):
        provider = OpenRouterProvider()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": '{"qualification": "10th", "category": "Railway"}'}}]
        }
        with patch("requests.post", return_value=mock_response):
            filters = provider.parse_job_query("10th pass railway jobs")
        self.assertEqual(filters, {"qualification": "10th", "category": "Railway"})


class ProviderSwitchingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="switchuser",
            email="switchuser@example.com",
            password="testpass123",
        )
        self.client = Client()
        self.client.force_login(self.user)

    @override_settings(
        AI_ENABLED=True,
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="gemini-3.8-flash",
        OPENROUTER_API_KEY="sk-or-v1-testkey1234567890abcdef",
        OPENROUTER_MODEL="nvidia/nemotron-3-ultra-550b-a55b-20260604",
    )
    def test_dynamic_switching_gemini_to_openrouter_and_back(self):
        # 1. Start with Gemini
        with override_settings(AI_PROVIDER="gemini"):
            provider_1 = get_ai_provider()
            self.assertIsInstance(provider_1, GeminiProvider)
            self.assertEqual(provider_1.model_name, "gemini-3.8-flash")
            status_1 = get_ai_status()
            self.assertEqual(status_1["provider"], "gemini")
            self.assertEqual(status_1["model"], "gemini-3.8-flash")

        # 2. Switch to OpenRouter
        with override_settings(AI_PROVIDER="openrouter"):
            provider_2 = get_ai_provider()
            self.assertIsInstance(provider_2, OpenRouterProvider)
            self.assertEqual(provider_2.model_name, "nvidia/nemotron-3-ultra-550b-a55b-20260604")
            status_2 = get_ai_status()
            self.assertEqual(status_2["provider"], "openrouter")
            self.assertEqual(status_2["model"], "nvidia/nemotron-3-ultra-550b-a55b-20260604")

        # 3. Switch back to Gemini
        with override_settings(AI_PROVIDER="gemini"):
            provider_3 = get_ai_provider()
            self.assertIsInstance(provider_3, GeminiProvider)
            self.assertEqual(provider_3.model_name, "gemini-3.8-flash")
            status_3 = get_ai_status()
            self.assertEqual(status_3["provider"], "gemini")
            self.assertEqual(status_3["model"], "gemini-3.8-flash")

    @override_settings(
        AI_ENABLED=True,
        GEMINI_API_KEY="gemini_test_key_0123456789",
        GEMINI_MODEL="gemini-3.8-flash",
        OPENROUTER_API_KEY="sk-or-v1-testkey1234567890abcdef",
        OPENROUTER_MODEL="nvidia/nemotron-3-ultra-550b-a55b-20260604",
    )
    def test_chat_api_endpoint_reflects_switched_provider(self):
        url = reverse("ai_assistant:chat")

        # 1. Gemini
        with override_settings(AI_PROVIDER="gemini"):
            mock_gemini = MagicMock()
            mock_gemini.is_configured.return_value = (True, "Gemini ready")
            mock_gemini.generate_chat_response.return_value = "Response from Gemini"
            with patch("ai_assistant.views.get_ai_provider", return_value=mock_gemini):
                resp1 = self.client.post(
                    url,
                    data=json.dumps({"message": "Hello"}),
                    content_type="application/json",
                )
                self.assertEqual(resp1.status_code, 200)
                data1 = resp1.json()
                self.assertEqual(data1["provider"], "gemini")
                self.assertEqual(data1["reply"], "Response from Gemini")

        # 2. Switch to OpenRouter
        with override_settings(AI_PROVIDER="openrouter"):
            mock_or = MagicMock()
            mock_or.is_configured.return_value = (True, "OpenRouter ready")
            mock_or.generate_chat_response.return_value = "Response from OpenRouter Nemotron"
            with patch("ai_assistant.views.get_ai_provider", return_value=mock_or):
                resp2 = self.client.post(
                    url,
                    data=json.dumps({"message": "Hello"}),
                    content_type="application/json",
                )
                self.assertEqual(resp2.status_code, 200)
                data2 = resp2.json()
                self.assertEqual(data2["provider"], "openrouter")
                self.assertEqual(data2["reply"], "Response from OpenRouter Nemotron")

        # 3. Switch back to Gemini
        with override_settings(AI_PROVIDER="gemini"):
            mock_gemini = MagicMock()
            mock_gemini.is_configured.return_value = (True, "Gemini ready")
            mock_gemini.generate_chat_response.return_value = "Response from Gemini second time"
            with patch("ai_assistant.views.get_ai_provider", return_value=mock_gemini):
                resp3 = self.client.post(
                    url,
                    data=json.dumps({"message": "Hello"}),
                    content_type="application/json",
                )
                self.assertEqual(resp3.status_code, 200)
                data3 = resp3.json()
                self.assertEqual(data3["provider"], "gemini")
                self.assertEqual(data3["reply"], "Response from Gemini second time")


# Six configured API configurations: two Gemini accounts that share one model
# id, three OpenRouter accounts with distinct model ids, and one Grok account.
# The values below are obviously fake test keys, never real credentials.
SIX_CONFIGURATION_ENV = """\
# --- Gemini account 1 ---
GEMINI_API_KEY=test-gemini-key-account-1
GEMINI_MODEL=gemini-3.8-flash

# --- OpenRouter account 1 ---
OPENROUTER_API_KEY=test-openrouter-key-account-1
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b-20260604

# --- Gemini account 2 ---
GEMINI_API_KEY=test-gemini-key-account-2
GEMINI_MODEL=gemini-3.8-flash

# --- OpenRouter account 2 ---
OPENROUTER_API_KEY=test-openrouter-key-account-2
OPENROUTER_MODEL=nvidia/nemotron-3.5-super-vl:free

# --- Grok account 1 ---
GROK_API_KEY=test-grok-key-account-1
GROK_MODEL=grok-4.7

# --- OpenRouter account 3 ---
OPENROUTER_API_KEY=test-openrouter-key-account-3
OPENROUTER_MODEL=minimax/minimax-m3.1-flash:free
"""

SIX_CONFIGURATION_IDS = [
    "gemini:gemini-3.8-flash#1",
    "gemini:gemini-3.8-flash#2",
    "openrouter:nvidia/nemotron-3-ultra-550b-a55b-20260604",
    "openrouter:nvidia/nemotron-3.5-super-vl:free",
    "openrouter:minimax/minimax-m3.1-flash:free",
    "grok:grok-4.7",
]


class MultiAccountRegistryTests(SimpleTestCase):
    """The ``.env`` allowlist keeps every repeated provider block as an account."""

    def setUp(self):
        cache.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.env_path = Path(self._tmp.name) / ".env"
        self.env_path.write_text(SIX_CONFIGURATION_ENV, encoding="utf-8")

    def _env_settings(self, **overrides):
        """Override settings so the temp file, not the developer's .env, wins."""
        values = {
            "AI_MODEL_ENV_FILE": str(self.env_path),
            "AI_ENABLED": True,
            "AI_PROVIDER": "gemini",
            "GEMINI_MODEL": "gemini-3.8-flash",
            "GEMINI_MODEL_EXPLICIT": True,
            "OPENROUTER_MODEL": "minimax/minimax-m3.1-flash:free",
            "OPENROUTER_MODEL_EXPLICIT": True,
            "GROK_MODEL": "grok-4.7",
            "GROK_MODEL_EXPLICIT": True,
            "OPENAI_MODEL_EXPLICIT": False,
        }
        values.update(overrides)
        return self.settings(**values)

    def _write_env(self, text):
        self.env_path.write_text(text, encoding="utf-8")

    # -- parsing -----------------------------------------------------------

    def test_repeated_variables_are_kept_in_file_order(self):
        occurrences = parse_env_occurrences(SIX_CONFIGURATION_ENV)
        self.assertEqual(
            [name for name, _ in occurrences if name == "GEMINI_API_KEY"],
            ["GEMINI_API_KEY", "GEMINI_API_KEY"],
        )
        blocks = blocks_from_env_occurrences(occurrences)
        self.assertEqual(
            blocks["gemini"],
            [
                ("test-gemini-key-account-1", "gemini-3.8-flash"),
                ("test-gemini-key-account-2", "gemini-3.8-flash"),
            ],
        )
        self.assertEqual(len(blocks["openrouter"]), 3)
        self.assertEqual(blocks["grok"], [("test-grok-key-account-1", "grok-4.7")])
        self.assertEqual(blocks["openai"], [])

    def test_comma_separated_model_list_registers_every_model(self):
        entries, errors = build_registry(
            {"gemini": [("test-key", "gemini-a, gemini-b ,gemini-a")]}
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            [(entry["provider"], entry["model"]) for entry in entries],
            [("gemini", "gemini-a"), ("gemini", "gemini-b")],
        )

    def test_invalid_model_id_is_reported_instead_of_silently_dropped(self):
        entries, errors = build_registry({"gemini": [("test-key", "not a valid id")]})
        self.assertEqual(entries, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("not a valid model ID", errors[0])

    def test_key_declared_without_a_model_is_reported(self):
        entries, errors = build_registry({"grok": [("test-key", "")]})
        self.assertEqual(entries, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("key but no model", errors[0])
        # A block with neither key nor model is simply absent, not an error.
        self.assertEqual(build_registry({"grok": [("", "")]}), ([], []))

    # -- registration ------------------------------------------------------

    def test_six_configurations_and_five_distinct_models_are_registered(self):
        with self._env_settings():
            registry = get_registry()
        self.assertEqual(len(registry), 6)
        self.assertEqual([entry["id"] for entry in registry], SIX_CONFIGURATION_IDS)
        self.assertEqual(
            sorted({entry["model"] for entry in registry}),
            sorted(
                {
                    "gemini-3.8-flash",
                    "nvidia/nemotron-3-ultra-550b-a55b-20260604",
                    "nvidia/nemotron-3.5-super-vl:free",
                    "minimax/minimax-m3.1-flash:free",
                    "grok-4.7",
                }
            ),
        )

    def test_identical_model_ids_on_repeated_accounts_keep_their_own_key(self):
        with self._env_settings():
            registry = get_registry()
        gemini = [entry for entry in registry if entry["provider"] == "gemini"]
        self.assertEqual(
            [entry["api_key"] for entry in gemini],
            ["test-gemini-key-account-1", "test-gemini-key-account-2"],
        )
        self.assertEqual(
            [entry["label"] for entry in gemini],
            [
                "Gemini — gemini-3.8-flash (account 1)",
                "Gemini — gemini-3.8-flash (account 2)",
            ],
        )

    def test_duplicate_model_id_on_one_provider_is_not_overwritten(self):
        entries, errors = build_registry(
            {"openrouter": [("key-a", "vendor/shared"), ("key-b", "vendor/shared")]}
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            [entry["id"] for entry in entries],
            ["openrouter:vendor/shared#1", "openrouter:vendor/shared#2"],
        )
        self.assertEqual([entry["api_key"] for entry in entries], ["key-a", "key-b"])

    def test_duplicate_model_id_across_providers_stays_provider_qualified(self):
        entries, errors = build_registry(
            {"gemini": [("key-a", "shared")], "openrouter": [("key-b", "shared")]}
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            [entry["id"] for entry in entries],
            ["gemini:shared", "openrouter:shared"],
        )

    def test_public_payload_exposes_no_credentials(self):
        with self._env_settings():
            models, errors = get_model_configuration()
        self.assertEqual(errors, [])
        self.assertEqual(len(models), 6)
        payload = json.dumps(models)
        for secret in (
            "test-gemini-key-account-1",
            "test-gemini-key-account-2",
            "test-openrouter-key-account-1",
            "test-grok-key-account-1",
        ):
            self.assertNotIn(secret, payload)
        self.assertNotIn("api_key", payload)

    def test_configuration_with_a_missing_key_stays_visible(self):
        self._write_env(
            "GEMINI_API_KEY=test-gemini-key-account-1\n"
            "GEMINI_MODEL=gemini-readable\n"
            "OPENROUTER_MODEL=vendor/no-key-model\n"
        )
        with self._env_settings(
            GEMINI_MODEL="gemini-readable",
            OPENROUTER_MODEL="vendor/no-key-model",
            GROK_MODEL_EXPLICIT=False,
        ):
            models, errors = get_model_configuration()
        self.assertEqual(errors, [])
        statuses = {model["model"]: model for model in models}
        self.assertEqual(statuses["gemini-readable"]["status"], "unknown")
        self.assertTrue(statuses["gemini-readable"]["configured"])
        self.assertEqual(statuses["vendor/no-key-model"]["status"], "missing_api_key")
        self.assertFalse(statuses["vendor/no-key-model"]["configured"])
        self.assertEqual(
            statuses["vendor/no-key-model"]["availability"], "Missing API key"
        )

    # -- routing -----------------------------------------------------------

    def test_config_id_selects_exactly_one_account(self):
        with self._env_settings():
            first = resolve_configuration(None, config_id="gemini:gemini-3.8-flash#1")
            second = resolve_configuration(None, config_id="gemini:gemini-3.8-flash#2")
        self.assertEqual(first["api_key"], "test-gemini-key-account-1")
        self.assertEqual(second["api_key"], "test-gemini-key-account-2")
        self.assertEqual(first["model"], second["model"])

    def test_unknown_selection_never_falls_back_to_another_account(self):
        with self._env_settings():
            self.assertIsNone(resolve_configuration(None, config_id="gemini:unknown#9"))
            self.assertIsNone(resolve_configuration("gemini", "unknown-model"))
            self.assertIsNone(resolve_configuration("unsupported", "gemini-3.8-flash"))
            self.assertIsNone(resolve_configuration("", None))
            self.assertIsNone(resolve_configuration("openai", "anything"))

    def test_chat_routes_config_id_to_the_exact_account_credential(self):
        request = RequestFactory().post(
            "/api/ai/chat/",
            data=json.dumps(
                {
                    "message": "Hello",
                    "config_id": "gemini:gemini-3.8-flash#2",
                    "provider": "gemini",
                    "model": "gemini-3.8-flash",
                }
            ),
            content_type="application/json",
        )
        request.user = type("AuthenticatedUser", (), {"is_authenticated": True})()
        provider = MagicMock()
        provider.api_key = "test-gemini-key-account-2"
        provider.is_configured.return_value = (True, "configured")
        provider.generate_chat_response.return_value = "Hello from account 2"
        with self._env_settings(), patch(
            "ai_assistant.views.get_ai_provider", return_value=provider
        ) as factory, patch(
            "ai_assistant.views.consume_daily_request", return_value=(True, 19)
        ):
            response = chat_api_view(request)
        self.assertEqual(response.status_code, 200)
        factory.assert_called_once_with(
            "gemini",
            api_key="test-gemini-key-account-2",
            model_name="gemini-3.8-flash",
        )
        self.assertEqual(json.loads(response.content)["provider"], "gemini")

    def test_chat_rejects_an_unknown_config_id_without_falling_back(self):
        request = RequestFactory().post(
            "/api/ai/chat/",
            data=json.dumps(
                {
                    "message": "Hello",
                    "config_id": "openrouter:not-configured",
                    "provider": "openrouter",
                    "model": "not-configured",
                }
            ),
            content_type="application/json",
        )
        request.user = type("AuthenticatedUser", (), {"is_authenticated": True})()
        with self._env_settings(), patch(
            "ai_assistant.views.get_ai_provider"
        ) as factory, patch("ai_assistant.views.consume_daily_request") as consume:
            response = chat_api_view(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content)["code"], "invalid_model")
        factory.assert_not_called()
        consume.assert_not_called()

    def test_models_endpoint_lists_every_configuration_without_secrets(self):
        request = RequestFactory().get("/api/ai/models/")
        request.user = type("AuthenticatedUser", (), {"is_authenticated": True})()
        with self._env_settings():
            response = ai_models_api_view(request)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        data = json.loads(body)
        self.assertEqual([model["id"] for model in data["models"]], SIX_CONFIGURATION_IDS)
        self.assertTrue(data["configured"])
        self.assertEqual(data["configuration_errors"], [])
        for secret in (
            "test-gemini-key-account-1",
            "test-gemini-key-account-2",
            "test-grok-key-account-1",
        ):
            self.assertNotIn(secret, body)
        self.assertNotIn("api_key", body)

    def test_models_endpoint_keeps_a_key_less_configuration_visible(self):
        self._write_env(
            "GEMINI_MODEL=gemini-without-key\nOPENROUTER_MODEL=vendor/no-key-model\n"
        )
        request = RequestFactory().get("/api/ai/models/")
        request.user = type("AuthenticatedUser", (), {"is_authenticated": True})()
        with self._env_settings(
            GEMINI_MODEL="gemini-without-key",
            OPENROUTER_MODEL="vendor/no-key-model",
            GROK_MODEL_EXPLICIT=False,
        ):
            response = ai_models_api_view(request)
        data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(data["configured"])
        self.assertEqual(
            [(model["model"], model["availability"]) for model in data["models"]],
            [
                ("gemini-without-key", "Missing API key"),
                ("vendor/no-key-model", "Missing API key"),
            ],
        )


class CheckModelControlRemovedTests(SimpleTestCase):
    """The user-facing Check Model control is gone; the rest of the UI remains."""

    def _read(self, *parts):
        return (Path(__file__).parent.joinpath(*parts)).read_text(encoding="utf-8")

    def test_rendered_widget_has_no_check_model_control(self):
        rendered = render_to_string("ai_assistant/chat_widget.html")
        self.assertNotIn("ai-model-check", rendered)
        self.assertNotIn("Check model", rendered)
        self.assertNotIn("Check availability", rendered)
        self.assertNotIn("models/check", rendered)

    def test_rendered_widget_keeps_the_useful_controls(self):
        rendered = render_to_string("ai_assistant/chat_widget.html")
        self.assertIn('id="ai-send-btn"', rendered)
        self.assertIn('id="ai-model-select"', rendered)
        self.assertIn('id="ai-model-retry"', rendered)
        self.assertIn('id="ai-reset-btn"', rendered)
        self.assertIn('id="ai-chat-form"', rendered)
        self.assertIn('id="ai-model-message"', rendered)
        # The removed button must not leave an empty placeholder behind.
        self.assertNotIn("ai-model-check", rendered)

    def test_frontend_script_has_no_check_model_handler(self):
        script = self._read("static", "ai_assistant", "chat_widget.js")
        self.assertNotIn("ai-model-check", script)
        self.assertNotIn("modelCheck", script)
        self.assertNotIn("models/check", script)
        self.assertNotIn("Check model", script)

    def test_frontend_script_still_wires_the_send_button_and_selector(self):
        script = self._read("static", "ai_assistant", "chat_widget.js")
        self.assertIn('document.getElementById("ai-send-btn")', script)
        self.assertIn('document.getElementById("ai-model-select")', script)
        self.assertIn('document.getElementById("ai-model-retry")', script)
        self.assertIn("async function sendMessage(text)", script)
        self.assertIn("config_id: selectedModel.id", script)

    def test_stylesheet_keeps_the_shared_retry_button_style(self):
        css = self._read("static", "ai_assistant", "chat_widget.css")
        self.assertIn(".ai-retry-btn", css)
        self.assertIn(".ai-send-btn", css)
        self.assertNotIn("ai-model-check", css)
