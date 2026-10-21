from dataclasses import dataclass
from datetime import date
from typing import Optional, List, Tuple

from django.utils import timezone
from .models import QUALIFICATION_DEFINITIONS, Job


QUALIFICATION_RANKS = {
    "10th": 1,
    "12th": 2,
    "iti": 2,
    "diploma": 3,
    "graduate": 4,
    "btech": 4,
    "postgraduate": 5,
}

QUALIFICATION_LABELS = {
    "10th": "10th Pass / Matriculation",
    "12th": "12th Pass / Intermediate",
    "iti": "ITI (Industrial Training)",
    "diploma": "Diploma / Polytechnic",
    "graduate": "Graduate / Bachelor's Degree",
    "btech": "B.Tech / B.E.",
    "postgraduate": "Postgraduate / Master's Degree",
}

QUALIFICATION_CODES = frozenset(code for code, _name, _rank in QUALIFICATION_DEFINITIONS)

# Eligibility status values produced by the dynamic eligibility engine.
ELIGIBILITY_ELIGIBLE = "eligible"
ELIGIBILITY_NOT_ELIGIBLE = "not_eligible"
ELIGIBILITY_INCOMPLETE = "incomplete"


def calculate_age(dob: date, cutoff_date: date) -> int:
    """Calculate age in completed years as of cutoff_date."""
    years = cutoff_date.year - dob.year
    if (cutoff_date.month, cutoff_date.day) < (dob.month, dob.day):
        years -= 1
    return years


def _qualification_tier_from_text(raw: str) -> Optional[str]:
    """Map free-text qualification wording to a standardized tier key."""
    raw = (raw or "").strip().lower()
    if not raw:
        return None

    if any(k in raw for k in ("post graduate", "postgraduate", "master", "m.tech", "m.sc", "m.a", "m.com")):
        return "postgraduate"
    if any(k in raw for k in ("graduate", "degree", "bachelor", "b.tech", "b.e", "b.sc", "b.com", "b.a")):
        return "graduate"
    if any(k in raw for k in ("diploma", "polytechnic")):
        return "diploma"
    if "iti" in raw:
        return "iti"
    if any(k in raw for k in ("12th", "intermediate", "higher secondary", "10+2")):
        return "12th"
    if any(k in raw for k in ("10th", "matric", "secondary", "high school")):
        return "10th"

    return None


def normalize_job_qualification(job: Job) -> Optional[str]:
    """
    Determine reliable standardized qualification tier for a job.

    Works with any exam-like object that exposes optional ``min_qualification``
    and ``qualification`` attributes. Returns standard key ('10th', '12th',
    etc.) or None if ambiguous/missing.
    """
    min_qualification = getattr(job, "min_qualification", None)
    if min_qualification:
        return min_qualification

    return _qualification_tier_from_text(getattr(job, "qualification", "") or "")


def _effective_cutoff_date(job) -> Tuple[date, str]:
    """Effective cutoff date for age display on any exam-like object."""
    cutoff = getattr(job, "age_cutoff_date", None)
    if cutoff:
        return cutoff, "official"
    application_end = getattr(job, "application_end_date", None)
    if application_end:
        return application_end, "application_deadline"
    return timezone.localdate(), "today"


def _has_age_criteria(job) -> bool:
    return (
        getattr(job, "min_age", None) is not None
        or getattr(job, "max_age", None) is not None
    )


def _age_criteria_display(job) -> str:
    min_age = getattr(job, "min_age", None)
    max_age = getattr(job, "max_age", None)
    if min_age is not None and max_age is not None:
        return f"{min_age} to {max_age} years"
    if min_age is not None:
        return f"Minimum {min_age} years"
    if max_age is not None:
        return f"Up to {max_age} years"
    return "Not configured"


def _dob_window(job) -> Tuple[Optional[date], Optional[date]]:
    return getattr(job, "dob_start_date", None), getattr(job, "dob_end_date", None)


def _has_dob_window(job) -> bool:
    dob_start, dob_end = _dob_window(job)
    return dob_start is not None or dob_end is not None


def _dob_window_display(job) -> str:
    dob_start, dob_end = _dob_window(job)
    if dob_start and dob_end:
        start = dob_start.strftime("%d %b %Y")
        end = dob_end.strftime("%d %b %Y")
        if dob_start == dob_end:
            return f"Born on {start} only"
        return f"Born between {start} and {end} (both inclusive)"
    if dob_start:
        return f"Born on or after {dob_start.strftime('%d %b %Y')}"
    if dob_end:
        return f"Born on or before {dob_end.strftime('%d %b %Y')}"
    return "Not configured"


def candidate_qualification_code(value: Optional[str]) -> Optional[str]:
    """
    Map a candidate's stored qualification to a canonical qualification code.

    Stored codes are used as-is; free-text values fall back to keyword matching.
    No hierarchy is assumed: a higher qualification does not automatically
    satisfy a lower requirement.
    """
    if not value:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    if raw in QUALIFICATION_CODES:
        return raw
    if any(k in raw for k in ("b.tech", "btech", "b.e.", "bachelor of engineering", "engineering degree")):
        return "btech"
    return _qualification_tier_from_text(raw)


def evaluate_qualification_match(candidate_tier: Optional[str], exam_tier: Optional[str]) -> Tuple[Optional[bool], str]:
    """
    Check candidate qualification against exam qualification.
    Returns (matches, status_text).
    matches is None if qualification not checked or exam criteria missing.
    """
    if not candidate_tier:
        return None, "Not evaluated (no qualification entered)"

    if not exam_tier:
        return None, "Criteria not configured in records — verify in official notification"

    cand_rank = QUALIFICATION_RANKS.get(candidate_tier, 0)
    exam_rank = QUALIFICATION_RANKS.get(exam_tier, 0)

    # ITI specific check
    if exam_tier == "iti":
        matched = (candidate_tier == "iti")
        label = QUALIFICATION_LABELS.get("iti", "ITI")
        return (matched, f"Requires {label}")

    # Diploma specific check: Diploma or higher degree
    if exam_tier == "diploma":
        matched = candidate_tier in {"diploma", "graduate", "postgraduate"}
        label = QUALIFICATION_LABELS.get("diploma", "Diploma")
        return (matched, f"Requires {label}")

    # Standard progression
    matched = cand_rank >= exam_rank
    label = QUALIFICATION_LABELS.get(exam_tier, exam_tier.capitalize())
    return (matched, f"Requires {label}")


@dataclass
class JobEligibilityResult:
    job: Job
    is_match: bool
    calculated_age: int
    cutoff_date: date
    cutoff_source: str  # 'official', 'application_deadline', 'today'
    age_matches: bool
    age_criteria_display: str
    qualification_matches: Optional[bool]
    qualification_criteria_display: str
    qualification_status: str
    status_badge: str
    status_description: str


def evaluate_job_eligibility(job: Job, dob: date, qualification: Optional[str] = None) -> JobEligibilityResult:
    """Evaluate candidate eligibility for a single job."""
    cutoff_date, cutoff_source = job.get_effective_cutoff_date()
    calculated_age = calculate_age(dob, cutoff_date)

    # 1. Age evaluation
    if not job.has_age_criteria:
        # Per specification: Handle missing criteria explicitly rather than silently treating as valid
        age_matches = False
        age_criteria_display = "Criteria not configured in records"
    else:
        age_matches = True
        if job.min_age is not None and calculated_age < job.min_age:
            age_matches = False
        if job.max_age is not None and calculated_age > job.max_age:
            age_matches = False
        age_criteria_display = job.age_criteria_display

    # 2. Qualification evaluation
    exam_tier = normalize_job_qualification(job)
    qual_matches, qual_status = evaluate_qualification_match(qualification, exam_tier)

    qualification_display = job.qualification
    if job.min_qualification:
        qualification_display = QUALIFICATION_LABELS.get(job.min_qualification, job.qualification)
    elif not qualification_display:
        qualification_display = "Not specified"

    # 3. Overall match determination
    is_match = False
    if age_matches:
        if qualification:
            if qual_matches is True:
                is_match = True
                status_badge = "Matches entered criteria"
                status_description = "Preliminary match based on entered age and qualification."
            elif qual_matches is None:
                # Age matches, but exam qualification data is unconfigured/unreliable
                is_match = True
                status_badge = "Age matches entered criteria"
                status_description = "Age matches entered criteria. Educational criteria not configured in records — verify in official notification."
            else:
                # Age matches but qualification fails
                is_match = False
                status_badge = "Qualification mismatch"
                status_description = "Does not satisfy educational requirement."
        else:
            # Qualification not supplied by candidate
            is_match = True
            status_badge = "Matches entered criteria"
            status_description = "Preliminary match based on entered age. Check official notification for required qualification."
    else:
        status_badge = "Does not match criteria"
        status_description = "Calculated age does not fall within the configured age criteria."

    return JobEligibilityResult(
        job=job,
        is_match=is_match,
        calculated_age=calculated_age,
        cutoff_date=cutoff_date,
        cutoff_source=cutoff_source,
        age_matches=age_matches,
        age_criteria_display=age_criteria_display,
        qualification_matches=qual_matches,
        qualification_criteria_display=qualification_display,
        qualification_status=qual_status,
        status_badge=status_badge,
        status_description=status_description,
    )


def check_eligibility_for_candidate(dob: date, qualification: Optional[str] = None) -> List[JobEligibilityResult]:
    """
    Evaluate all active, published, verified jobs against candidate credentials.
    Returns list of matching JobEligibilityResult items.
    """
    from .selectors import public_jobs_queryset

    active_jobs = public_jobs_queryset()
    matched_results = []

    for job in active_jobs:
        result = evaluate_job_eligibility(job, dob, qualification)
        if result.is_match:
            matched_results.append(result)

    return matched_results


@dataclass
class CandidateEligibilityResult:
    """Result of the dynamic (DOB window + accepted qualifications) evaluation."""

    job: Job
    status: str
    is_eligible: bool
    dob_matches: Optional[bool]
    qualification_matches: Optional[bool]
    dob_criteria_display: str
    qualification_criteria_display: str
    qualification_status: str
    status_badge: str
    status_description: str
    calculated_age: Optional[int]
    cutoff_date: date
    cutoff_source: str
    age_criteria_display: str

    @property
    def is_incomplete(self) -> bool:
        return self.status == ELIGIBILITY_INCOMPLETE


def selected_qualifications(job: Job) -> List:
    """Qualifications the admin selected for this exam (empty when unconfigured)."""
    if not job.pk:
        return []
    return list(job.eligible_qualifications.all())


def evaluate_candidate_eligibility(
    job: Job,
    dob: Optional[date] = None,
    qualification: Optional[str] = None,
) -> CandidateEligibilityResult:
    """
    Evaluate one exam for a candidate using the dynamic eligibility rules.

    DOB condition: ``dob_start_date <= dob <= dob_end_date`` (both inclusive).
    Qualification condition: the candidate's qualification must match at least
    one qualification selected by the admin for the exam.

    Exams that have no DOB window/qualifications selected fall back to the
    legacy age-range and qualification-tier criteria so older records keep
    working. A condition that cannot be verified (missing candidate data or
    missing exam criteria) is reported as "incomplete" rather than eligible.
    """
    cutoff_date, cutoff_source = _effective_cutoff_date(job)
    calculated_age = calculate_age(dob, cutoff_date) if dob else None

    qualifications = selected_qualifications(job)
    dob_start, dob_end = _dob_window(job)

    # --- DOB condition ---
    if _has_dob_window(job):
        dob_criteria_display = _dob_window_display(job)
        if dob is None:
            dob_matches = None
        else:
            dob_matches = True
            if dob_start and dob < dob_start:
                dob_matches = False
            if dob_end and dob > dob_end:
                dob_matches = False
        dob_configured = True
    elif _has_age_criteria(job):
        dob_criteria_display = _age_criteria_display(job)
        min_age = getattr(job, "min_age", None)
        max_age = getattr(job, "max_age", None)
        if dob is None:
            dob_matches = None
        else:
            dob_matches = True
            if min_age is not None and calculated_age < min_age:
                dob_matches = False
            if max_age is not None and calculated_age > max_age:
                dob_matches = False
        dob_configured = True
    else:
        dob_criteria_display = "Not configured"
        dob_matches = None
        dob_configured = False

    # --- Qualification condition ---
    if qualifications:
        qualification_criteria_display = ", ".join(
            item.name for item in qualifications
        )
        accepted_codes = {item.code for item in qualifications}
        candidate_code = candidate_qualification_code(qualification)
        if not qualification:
            qualification_matches = None
            qualification_status = "Not evaluated (no qualification entered)"
        elif candidate_code in accepted_codes:
            qualification_matches = True
            qualification_status = "Your qualification is accepted for this exam."
        else:
            qualification_matches = False
            qualification_status = (
                "Requires one of: " + qualification_criteria_display
            )
        qualification_configured = True
    else:
        legacy_tier = normalize_job_qualification(job)
        min_qualification = getattr(job, "min_qualification", None)
        raw_qualification = getattr(job, "qualification", "") or ""
        if min_qualification:
            qualification_criteria_display = QUALIFICATION_LABELS.get(
                min_qualification, raw_qualification
            )
        else:
            qualification_criteria_display = raw_qualification or "Not specified"
        if not qualification:
            qualification_matches = None
            qualification_status = "Not evaluated (no qualification entered)"
        else:
            qualification_matches, qualification_status = evaluate_qualification_match(
                qualification, legacy_tier
            )
        qualification_configured = bool(legacy_tier)

    # --- Combined outcome ---
    # A condition that cannot be verified (missing candidate data or missing
    # exam criteria) is never reported as eligible.
    if dob_configured and dob_matches is False:
        status = ELIGIBILITY_NOT_ELIGIBLE
        status_badge = "Date of birth does not match"
        status_description = (
            "Your date of birth is outside this exam's eligible window "
            f"({dob_criteria_display})."
        )
    elif qualification_configured and qualification_matches is False:
        status = ELIGIBILITY_NOT_ELIGIBLE
        status_badge = "Qualification does not match"
        status_description = (
            "Your recorded qualification is not one of the qualifications "
            "accepted for this exam."
        )
    elif not dob_configured or not qualification_configured:
        # The exam is missing part (or all) of its eligibility configuration,
        # so eligibility cannot be confirmed either way.
        status = ELIGIBILITY_INCOMPLETE
        status_badge = "Eligibility unverified"
        status_description = (
            "Eligibility criteria have not been fully recorded for this exam yet. "
            "Verify the requirements in the official notification."
        )
    elif dob_matches is None or qualification_matches is None:
        status = ELIGIBILITY_INCOMPLETE
        status_badge = "Eligibility incomplete"
        status_description = (
            "Add your date of birth and qualification to your profile to verify "
            "eligibility for this exam."
        )
    else:
        status = ELIGIBILITY_ELIGIBLE
        status_badge = "Eligible"
        status_description = (
            "Your date of birth and recorded qualification match the criteria "
            "configured for this exam."
        )

    return CandidateEligibilityResult(
        job=job,
        status=status,
        is_eligible=status == ELIGIBILITY_ELIGIBLE,
        dob_matches=dob_matches,
        qualification_matches=qualification_matches,
        dob_criteria_display=dob_criteria_display,
        qualification_criteria_display=qualification_criteria_display,
        qualification_status=qualification_status,
        status_badge=status_badge,
        status_description=status_description,
        calculated_age=calculated_age,
        cutoff_date=cutoff_date,
        cutoff_source=cutoff_source,
        age_criteria_display=_age_criteria_display(job),
    )


def evaluate_eligibility_for_candidate(
    dob: Optional[date] = None,
    qualification: Optional[str] = None,
    jobs=None,
) -> Tuple[List[CandidateEligibilityResult], List[CandidateEligibilityResult]]:
    """
    Evaluate every publicly listed exam for a candidate.

    Returns ``(eligible_results, incomplete_results)``. Exams where the DOB or
    qualification clearly do not match are excluded from both lists.
    """
    from .selectors import public_jobs_queryset

    active_jobs = jobs if jobs is not None else public_jobs_queryset()
    eligible_results: List[CandidateEligibilityResult] = []
    incomplete_results: List[CandidateEligibilityResult] = []

    for job in active_jobs:
        result = evaluate_candidate_eligibility(job, dob, qualification)
        if result.status == ELIGIBILITY_ELIGIBLE:
            eligible_results.append(result)
        elif result.status == ELIGIBILITY_INCOMPLETE:
            incomplete_results.append(result)

    return eligible_results, incomplete_results


def evaluate_eligibility_for_user(user, jobs=None):
    """Build eligibility results from the signed-in user's saved profile data."""
    return evaluate_eligibility_for_candidate(
        dob=getattr(user, "date_of_birth", None),
        qualification=getattr(user, "qualification", None) or None,
        jobs=jobs,
    )
