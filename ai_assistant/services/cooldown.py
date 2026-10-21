import time
from typing import Any, Dict, Optional

from django.core.cache import cache


class KeyCooldownTracker:
    """
    Cache-backed cooldown manager for rate-limited API keys and providers.

    When a provider or key encounters HTTP 429 / quota exhaustion (RESOURCE_EXHAUSTED),
    it is placed on a temporary cooldown (default: 60 seconds). During this cooldown,
    incoming requests skip this key and try the next configured fallback key or provider,
    avoiding redundant failing calls and latency.

    Keys are NEVER permanently disabled by transient errors. Once the cooldown
    expires, the key is automatically available again for subsequent requests.

    Backing store: Django cache. This ensures:
    1. Cooldown state is thread-safe and process-safe.
    2. Automatic time-based expiration.
    3. Test isolation when cache.clear() is called in setUp().
    """

    def __init__(self, default_cooldown_seconds: int = 60):
        self.default_cooldown_seconds = default_cooldown_seconds
        self._prefix = "ai:cooldown:"

    def _cache_key(self, key_id: str) -> str:
        return f"{self._prefix}{key_id}"

    def is_cooling_down(self, key_id: str) -> bool:
        """Return True if key_id is currently within its cooldown window."""
        expiry = cache.get(self._cache_key(key_id))
        if expiry is None:
            return False
        if time.time() >= expiry:
            cache.delete(self._cache_key(key_id))
            return False
        return True

    def mark_rate_limited(
        self, key_id: str, cooldown_seconds: Optional[int] = None
    ) -> float:
        """
        Mark key_id as rate-limited until now + cooldown_seconds.
        Returns the absolute expiry timestamp.
        """
        duration = (
            cooldown_seconds
            if cooldown_seconds is not None
            else self.default_cooldown_seconds
        )
        expiry = time.time() + duration
        cache.set(self._cache_key(key_id), expiry, timeout=duration)
        return expiry

    def get_remaining_seconds(self, key_id: str) -> float:
        """Return remaining seconds of cooldown, or 0.0 if not cooling down."""
        expiry = cache.get(self._cache_key(key_id))
        if expiry is None:
            return 0.0
        remaining = expiry - time.time()
        if remaining <= 0:
            cache.delete(self._cache_key(key_id))
            return 0.0
        return round(remaining, 1)

    def clear(self, key_id: Optional[str] = None):
        """Clear cooldown for key_id or all keys if key_id is None."""
        if key_id is not None:
            cache.delete(self._cache_key(key_id))
        else:
            # Clear standard known keys
            for idx in (1, 2, 3):
                cache.delete(self._cache_key(f"gemini_key_{idx}"))
            cache.delete(self._cache_key("openrouter"))

    def status(self) -> Dict[str, Dict[str, Any]]:
        """Return a snapshot of active cooldowns for known keys."""
        active: Dict[str, Dict[str, Any]] = {}
        for key_id in ("gemini_key_1", "gemini_key_2", "gemini_key_3", "openrouter"):
            if self.is_cooling_down(key_id):
                active[key_id] = {
                    "in_cooldown": True,
                    "remaining_seconds": self.get_remaining_seconds(key_id),
                }
        return active


# Global singleton instance for the running server process
global_cooldown_tracker = KeyCooldownTracker(default_cooldown_seconds=60)
