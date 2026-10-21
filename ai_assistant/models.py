from django.conf import settings
from django.db import models


class AIDailyUsage(models.Model):
    """
    Tracks per-user daily AI request consumption.

    Each (user, usage_date) pair is unique. The request_count is incremented
    atomically for every AI request that passes validation and reaches the
    provider invocation. The counter resets naturally by calendar date in the
    project's configured Django timezone.

    Counting policy (see ratelimit.consume_daily_request):
    - Anonymous requests (HTTP 401) are NEVER counted.
    - Invalid payloads (HTTP 400) are NEVER counted.
    - Requests that reach the AI provider (success OR provider failure/503)
      ARE counted, because they consume an AI attempt.
    - A user-initiated retry is a brand-new request and counts separately.
    - The /status/ endpoint never consumes quota.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_daily_usages",
    )
    usage_date = models.DateField(db_index=True)
    request_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "usage_date"],
                name="ai_daily_usage_user_date_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "usage_date"]),
        ]
        verbose_name = "AI Daily Usage"
        verbose_name_plural = "AI Daily Usages"

    def __str__(self):
        return f"{self.user} - {self.usage_date} ({self.request_count})"
