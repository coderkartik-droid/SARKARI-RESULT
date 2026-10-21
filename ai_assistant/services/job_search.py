import re
import logging
from typing import Any, Dict, List, Tuple
from django.conf import settings
from django.db.models import Q
from jobs.models import Job
from . import get_ai_provider


logger = logging.getLogger(__name__)
FILTER_VALUE_PATTERN = re.compile(r"[\w\s.,&()/+-]{1,80}", re.UNICODE)

STOP_WORDS = {
    "in", "for", "the", "a", "an", "and", "or", "to", "of", "jobs", "job", "vacancy",
    "vacancies", "recruitment", "form", "notification", "latest", "sarkari", "govt",
    "government", "apply", "online", "find", "search", "show", "me", "any", "all",
}

COMMON_ORGANIZATIONS = {
    "ssc": "SSC",
    "upsc": "UPSC",
    "railway": "Railway",
    "railways": "Railway",
    "rrb": "Railway",
    "ibps": "IBPS",
    "sbi": "SBI",
    "drdo": "DRDO",
    "isro": "ISRO",
    "nda": "NDA",
    "cds": "CDS",
    "afcat": "AFCAT",
    "kvs": "KVS",
    "nvs": "NVS",
}

COMMON_QUALIFICATIONS = {
    "10th": "10th",
    "matric": "10th",
    "10th pass": "10th",
    "12th": "12th",
    "inter": "12th",
    "intermediate": "12th",
    "12th pass": "12th",
    "graduate": "Graduate",
    "graduation": "Graduate",
    "degree": "Graduate",
    "btech": "B.Tech",
    "b.tech": "B.Tech",
    "engineering": "Engineering",
    "diploma": "Diploma",
    "bed": "B.Ed",
    "b.ed": "B.Ed",
}

COMMON_CATEGORIES = {
    "railway": "Railway",
    "railways": "Railway",
    "defence": "Defence",
    "defense": "Defence",
    "army": "Defence",
    "navy": "Defence",
    "airforce": "Defence",
    "police": "Police",
    "banking": "Banking",
    "bank": "Banking",
    "teaching": "Teaching",
    "teacher": "Teaching",
}


def rule_based_extract(query: str) -> Dict[str, str]:
    """
    Fast, deterministic heuristic extractor that operates offline
    without requiring any LLM call.
    """
    clean_query = query.strip()
    words = re.findall(r"\b[\w.-]+\b", clean_query.casefold())

    filters: Dict[str, str] = {}

    # Extract qualification
    for k, v in COMMON_QUALIFICATIONS.items():
        if k in clean_query.casefold():
            filters["qualification"] = v
            break

    # Extract organization
    for k, v in COMMON_ORGANIZATIONS.items():
        if k in words:
            filters["organization"] = v
            break

    # Extract category
    for k, v in COMMON_CATEGORIES.items():
        if k in words:
            filters["category"] = v
            break

    # Remaining significant words form keyword
    filtered_words = [
        w for w in words
        if w not in STOP_WORDS
        and w not in COMMON_ORGANIZATIONS
        and w not in COMMON_CATEGORIES
        and w not in COMMON_QUALIFICATIONS
    ]
    if filtered_words:
        filters["keyword"] = " ".join(filtered_words[:4])

    return filters


def parse_and_validate_filters(query: str) -> Dict[str, str]:
    """
    Interprets natural language query using AI when available and enabled,
    with safe fallback to heuristic extraction. All returned filters are strictly validated.
    """
    filters: Dict[str, str] = {}
    is_enabled = getattr(settings, "AI_ENABLED", False)

    if is_enabled:
        try:
            provider = get_ai_provider()
            is_ready, _ = provider.is_configured()
            if is_ready:
                ai_filters = provider.parse_job_query(query)
                if isinstance(ai_filters, dict):
                    filters = sanitize_filters(ai_filters)
        except Exception as exc:
            logger.warning(
                "AI job-query interpretation failed (%s); using local parsing.",
                type(exc).__name__,
            )

    # If AI produced no or few filters, complement with rule-based extraction
    if not filters:
        filters = rule_based_extract(query)

    return filters


def sanitize_filters(raw_filters: Any) -> Dict[str, str]:
    """Keep only bounded, plain-text filters before they reach ORM lookups."""
    if not isinstance(raw_filters, dict):
        return {}

    safe_filters: Dict[str, str] = {}
    for key in ("keyword", "organization", "qualification", "location", "category"):
        value = raw_filters.get(key)
        if not isinstance(value, str):
            continue
        normalized = " ".join(value.split())
        if not normalized or len(normalized) > 80:
            continue
        if not FILTER_VALUE_PATTERN.fullmatch(normalized):
            continue
        # Drop generic stop words from the keyword so an AI-returned term like
        # "jobs" does not exclude every record that does not literally contain it.
        if key == "keyword":
            kept = [
                w for w in normalized.split()
                if w.casefold() not in STOP_WORDS
            ]
            normalized = " ".join(kept)
            if not normalized:
                continue
        safe_filters[key] = normalized
    return safe_filters


def search_jobs(
    query: str,
    page: int = 1,
    limit: int = 10,
    filters_override: Dict[str, str] = None,
) -> Tuple[List[Dict[str, Any]], int, Dict[str, str]]:
    """
    Executes a secure, parameterized Django ORM search for verified published jobs.
    Never executes arbitrary SQL or raw queries.
    Never fabricates mock jobs.
    """
    query = (query or "").strip()[:200]
    filters = sanitize_filters(filters_override) if filters_override is not None else (
        parse_and_validate_filters(query) if query else {}
    )

    qs = Job.objects.filter(status="published", is_verified=True)

    # Build standard Q objects safely
    q_conditions = Q()

    keyword = filters.get("keyword", "").strip()
    if keyword:
        q_conditions &= (
            Q(title__icontains=keyword)
            | Q(organization__icontains=keyword)
            | Q(qualification__icontains=keyword)
            | Q(location__icontains=keyword)
        )

    organization = filters.get("organization", "").strip()
    if organization:
        q_conditions &= (
            Q(organization__icontains=organization)
            | Q(title__icontains=organization)
        )

    qualification = filters.get("qualification", "").strip()
    if qualification:
        q_conditions &= Q(qualification__icontains=qualification)

    location = filters.get("location", "").strip()
    if location:
        q_conditions &= Q(location__icontains=location)

    category = filters.get("category", "").strip()
    if category:
        q_conditions &= (
            Q(category__icontains=category)
            | Q(title__icontains=category)
        )

    if q_conditions:
        qs = qs.filter(q_conditions)

    # Order: active non-expired first, then newest
    qs = qs.order_by("is_expired", "-application_end_date", "-created_at")

    total_count = qs.count()

    # Pagination bounds
    limit = max(1, min(limit, 25))
    page = max(1, page)
    start = (page - 1) * limit
    end = start + limit

    results = [] if start >= total_count else [job.to_dict() for job in qs[start:end]]

    return results, total_count, filters
