from django.db.models import Q
from django.utils import timezone

from .models import Job


def public_jobs_queryset():
    """Return published, verified jobs that have not passed their deadline."""
    return (
        Job.objects.filter(
            status="published",
            is_verified=True,
            is_expired=False,
        )
        .filter(
            Q(application_end_date__isnull=True)
            | Q(application_end_date__gte=timezone.localdate())
        )
        .order_by("-created_at", "-pk")
    )
