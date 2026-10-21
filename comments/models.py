from django.conf import settings
from django.db import models


class Comment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        PUBLISHED = "published", "Published"
        REJECTED = "rejected", "Rejected"

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_comments",
    )
    body = models.TextField(max_length=2000)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "community comment"
        verbose_name_plural = "community comments"

    def __str__(self):
        return f"Comment by {self.author} ({self.get_status_display()})"
