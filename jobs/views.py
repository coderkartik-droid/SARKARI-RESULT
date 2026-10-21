from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from accounts.views import _public_footer_context, _public_navigation_sections
from .models import Job
from .selectors import public_jobs_queryset
from site_management.models import WebsiteSettings


JOBS_PAGE_SIZE = 20


def job_list(request):
    jobs = public_jobs_queryset()
    query = request.GET.get("q", "").strip()[:120]
    if query:
        jobs = jobs.filter(
            Q(title__icontains=query)
            | Q(organization__icontains=query)
            | Q(qualification__icontains=query)
            | Q(location__icontains=query)
            | Q(category__icontains=query)
        )
    page = Paginator(jobs, JOBS_PAGE_SIZE).get_page(request.GET.get("page"))
    return render(
        request,
        "jobs/job_list.html",
        {
            "page_obj": page,
            "query": query,
            "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
            "navigation_sections": _public_navigation_sections(),
            **_public_footer_context(),
        },
    )


def job_detail(request, pk):
    from .eligibility import evaluate_candidate_eligibility

    job = get_object_or_404(public_jobs_queryset(), pk=pk)
    job_eligibility = None
    user = request.user
    if user.is_authenticated and getattr(user, "date_of_birth", None):
        job_eligibility = evaluate_candidate_eligibility(
            job,
            dob=user.date_of_birth,
            qualification=user.qualification or None,
        )
    return render(
        request,
        "jobs/job_detail.html",
        {
            "job": job,
            "job_eligibility": job_eligibility,
            "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
            "navigation_sections": _public_navigation_sections(),
            **_public_footer_context(),
        },
    )


def job_detail_json(request, pk):
    job = get_object_or_404(
        Job.objects.filter(status="published", is_verified=True),
        pk=pk,
    )
    return JsonResponse({"job": job.to_dict()})


def _eligibility_result_item(outcome, obj, kind, detail_url):
    """Normalise an eligibility outcome into a template-friendly row.

    The shared engine returns a result whose ``job`` attribute is either an
    :class:`site_management.models.Exam` or a :class:`jobs.models.Job`, so the
    row carries only the fields both content types share plus the correct,
    per-object detail URL.
    """
    return {
        "kind": kind,
        "action_label": "View Exam" if kind == "Exam" else "View Job",
        "title": obj.title,
        "detail_url": detail_url,
        "summary": (getattr(obj, "description", "") or "").strip(),
        "organization": getattr(obj, "organization", "") or "",
        "location": getattr(obj, "location", "") or "",
        "dob_criteria_display": outcome.dob_criteria_display,
        "qualification_criteria_display": outcome.qualification_criteria_display,
        "qualification_status": outcome.qualification_status,
        "status_badge": outcome.status_badge,
        "status_description": outcome.status_description,
        "official_notification_url": getattr(obj, "official_notification_url", "") or "",
        "published_at": getattr(obj, "publish_at", None) or getattr(obj, "created_at", None),
    }


def eligibility_check(request):
    """Check which published exams and jobs match the submitted DOB/qualification.

    The two form values are the only inputs used for the search. They are never
    written to (or read from) the signed-in user's profile — the profile merely
    pre-fills the fields. Only objects the shared eligibility engine marks
    eligible are placed in the results list.
    """
    from accounts.views import _published_exams_queryset

    from .eligibility import ELIGIBILITY_ELIGIBLE, ELIGIBILITY_INCOMPLETE
    from .eligibility import evaluate_candidate_eligibility
    from .forms import EligibilityCheckForm

    user = request.user if request.user.is_authenticated else None
    saved_dob = getattr(user, "date_of_birth", None) if user else None
    saved_qualification = (getattr(user, "qualification", "") or "") if user else ""

    # Saved profile values only pre-fill the form; they are never used for the
    # calculation and are never treated as submitted search values.
    initial = {}
    if saved_dob:
        initial["dob"] = saved_dob
    if saved_qualification:
        initial["qualification"] = saved_qualification

    submitted = request.method == "POST" or (
        bool(request.GET)
        and any(key in request.GET for key in ("dob", "qualification", "submit", "check"))
    )
    data = None
    if submitted:
        data = request.POST if request.method == "POST" else request.GET
    form = EligibilityCheckForm(data=data, initial=initial or None)

    evaluated = form.is_bound and form.is_valid()
    results = []
    incomplete_results = []
    candidate_dob = None
    candidate_qualification = None
    qualification_label = None

    if evaluated:
        candidate_dob = form.cleaned_data["dob"]
        candidate_qualification = form.cleaned_data.get("qualification") or None
        qualification_label = dict(form.fields["qualification"].choices).get(
            candidate_qualification
        )

        for exam in _published_exams_queryset():
            outcome = evaluate_candidate_eligibility(
                exam, candidate_dob, candidate_qualification
            )
            item = _eligibility_result_item(
                outcome, exam, "Exam", reverse("accounts:exam_detail", args=[exam.pk])
            )
            if outcome.status == ELIGIBILITY_ELIGIBLE:
                results.append(item)
            elif outcome.status == ELIGIBILITY_INCOMPLETE:
                incomplete_results.append(item)

        for job in public_jobs_queryset():
            outcome = evaluate_candidate_eligibility(
                job, candidate_dob, candidate_qualification
            )
            item = _eligibility_result_item(
                outcome, job, "Job", reverse("jobs:detail", args=[job.pk])
            )
            if outcome.status == ELIGIBILITY_ELIGIBLE:
                results.append(item)
            elif outcome.status == ELIGIBILITY_INCOMPLETE:
                incomplete_results.append(item)

    return render(
        request,
        "jobs/eligibility_check.html",
        {
            "form": form,
            "submitted": submitted,
            "evaluated": evaluated,
            "results": results,
            "incomplete_results": incomplete_results,
            "candidate_dob": candidate_dob,
            "candidate_qualification": candidate_qualification,
            "qualification_label": qualification_label,
            "profile_prefilled": bool(initial),
            "update_profile_url": reverse("accounts:dashboard"),
            "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
            "navigation_sections": _public_navigation_sections(),
            **_public_footer_context(),
        },
    )

