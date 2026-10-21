from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class AIProviderError(RuntimeError):
    """Base exception for AI provider errors."""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        status_code: Optional[int] = None,
        provider_error_code: Optional[str] = None,
        provider_error_type: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.status_code = status_code
        self.provider_error_code = provider_error_code
        self.provider_error_type = provider_error_type


class AIProviderTimeoutError(AIProviderError):
    """Raised when an AI provider request exceeds its configured timeout."""

    def __init__(
        self,
        message: str = "The AI assistant request timed out. Please try again.",
        provider: Optional[str] = None,
        status_code: Optional[int] = None,
    ):
        super().__init__(message, provider=provider, status_code=status_code)


class AIConfigurationError(AIProviderError):
    """Raised when an AI provider has invalid or missing configuration."""


class AIAuthenticationError(AIProviderError):
    """Raised when authentication with an AI provider fails."""


class AIPaymentRequiredError(AIProviderError):
    """Raised when an AI provider account has insufficient credits or requires payment."""


class AIQuotaExceededError(AIProviderError):
    """Raised when a provider explicitly reports exhausted quota."""


class AINetworkError(AIProviderError):
    """Raised when connectivity prevents a provider request."""


class AIModelNotFoundError(AIProviderError):
    """Raised when a requested model is not found on the AI provider."""


class AIRateLimitError(AIProviderError):
    """Raised when rate limits or quotas are exceeded on the AI provider."""


class AIServerError(AIProviderError):
    """Raised when an upstream AI provider server error occurs."""


class BaseAIProvider(ABC):
    """
    Abstract base class for AI providers.
    Ensures that the chat endpoint and jobs search logic are decoupled
    from any specific LLM provider (Gemini, OpenAI, Anthropic, etc.).
    """

    @abstractmethod
    def is_configured(self) -> Tuple[bool, str]:
        """
        Returns (is_ready, message).
        Checks if credentials and configuration are valid without exposing secrets.
        """
        pass

    @abstractmethod
    def list_models(self, timeout: int = 8) -> List[Dict[str, str]]:
        """Return models the provider reports as available for text generation."""
        pass

    @abstractmethod
    def generate_chat_response(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        timeout: int = 15,
        model_name: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
    ) -> str:
        """
        Generates a text completion/response from the provider.
        messages: List of dicts with keys 'role' ('user'|'model'|'assistant') and 'content'.
        """
        pass

    @abstractmethod
    def parse_job_query(
        self,
        query: str,
        timeout: int = 10,
    ) -> Dict[str, Any]:
        """
        Interprets natural language search queries into validated structured filters.
        Returns a dictionary with sanitized keys like keyword, qualification, organization, etc.
        """
        pass
