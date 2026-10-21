"""
Per-user daily rate limiting for the AI assistant.

Implementation notes
--------------------
* Persistence: counters live in the database (``AIDailyUsage``), not in the
  Django cache, so they survive process restarts and worker restarts and are
  not vulnerable to cache eviction.
* Atomicity: ``consume_daily_request`` wraps the read-modify-write in a
  transaction and locks the per-user/per-day row with ``select_for_update``.
  The increment itself is a database-level ``F()`` expression, so two
  concurrent requests cannot both read the same value and both pass the
  limit check.
* Timezone: the "day" is computed with ``timezone.localdate()``, which uses
  the project's configured ``TIME_ZONE`` (Asia/Kolkata). The counter resets
  automatically at midnight in that timezone because each calendar date has
  its own row.
* What counts (see ``AIDailyUsage`` docstring): a request is counted once,
  after payload validation passes and immediately before the AI provider is
  invoked. Anonymous and invalid requests are never counted. A provider
  failure (HTTP 503) still counts because an AI attempt was consumed. A
  user-initiated retry is a new request and counts separately.
"""

import datetime

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone


def get_daily_limit() -> int:
    """Return the configured daily request limit (default 20).

    Reads ``settings.AI_DAILY_REQUEST_LIMIT`` at call time so that test
    overrides (``override_settings``) are honored.
    """
    return int(getattr(settings, "AI_DAILY_REQUEST_LIMIT", 20))


def today() -> "datetime.date":
    """Today's date in the project's configured Django timezone."""
    return timezone.localdate()


def consume_daily_request(user) -> tuple:
    """
    Atomically consume one daily AI request for ``user``.

    Returns ``(allowed, remaining)`` where:
    * ``allowed`` is True if the request is within the daily limit.
    * ``remaining`` is the number of requests left today (0 when not allowed).

    The row for (user, today) is created if missing, then locked with
    ``select_for_update``; the count is bumped with an ``F()`` expression so
    concurrent requests serialize on the database row.
    """
    from .models import AIDailyUsage

    limit = get_daily_limit()
    day = today()

    with transaction.atomic():
        usage, _created = AIDailyUsage.objects.get_or_create(
            user=user,
            usage_date=day,
            defaults={"request_count": 0},
        )
        # Re-fetch under an exclusive lock for an atomic check-and-increment.
        usage = AIDailyUsage.objects.select_for_update().get(pk=usage.pk)

        if usage.request_count >= limit:
            return False, max(0, limit - usage.request_count)

        usage.request_count = F("request_count") + 1
        usage.save(update_fields=["request_count", "updated_at"])
        usage.refresh_from_db()
        return True, max(0, limit - usage.request_count)


def get_remaining_requests(user) -> int:
    """Return how many requests ``user`` has left today (non-consuming)."""
    from .models import AIDailyUsage

    limit = get_daily_limit()
    try:
        usage = AIDailyUsage.objects.get(user=user, usage_date=today())
    except AIDailyUsage.DoesNotExist:
        return limit
    return max(0, limit - usage.request_count)
