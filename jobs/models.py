from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# Canonical qualification levels used for eligibility matching. Kept in sync with
# the qualification rows seeded by migration 0004_seed_default_qualifications.
QUALIFICATION_DEFINITIONS = [
    ("10th", "10th Pass / Matriculation", 1),
    ("12th", "12th Pass / Intermediate", 2),
    ("iti", "ITI (Industrial Training)", 2),
    ("diploma", "Diploma / Polytechnic", 3),
    ("graduate", "Graduate / Bachelor's Degree", 4),
    ("btech", "B.Tech / B.E.", 4),
    ("postgraduate", "Postgraduate / Master's Degree", 5),
]


class Qualification(models.Model):
    """A database-backed qualification level that exams can require."""

    code = models.SlugField(
        max_length=30,
        unique=True,
        help_text="Stable identifier used by the eligibility engine (e.g. '12th', 'graduate').",
    )
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Human-readable label shown in the admin and public pages.",
    )
    rank = models.PositiveSmallIntegerField(
        default=0,
        help_text="Relative level used for display ordering. Higher means a higher qualification.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive qualifications stay on existing exams but are hidden from new selections.",
    )

    class Meta:
        ordering = ["rank", "name"]
        verbose_name = "Qualification"
        verbose_name_plural = "Qualifications"

    def __str__(self):
        return self.name


class Job(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]

    QUALIFICATION_CHOICES = [
        ("10th", "10th"),
        ("12th", "12th"),
        ("iti", "ITI"),
        ("diploma", "Diploma"),
        ("graduate", "Graduate"),
        ("postgraduate", "Postgraduate"),
    ]

    title = models.CharField(
        max_length=255,
        help_text="e.g. SSC CGL 2026, RRB NTPC, UPSC Civil Services",
    )
    organization = models.CharField(
        max_length=255,
        help_text="e.g. Staff Selection Commission (SSC), Railway Recruitment Board (RRB)",
    )
    qualification = models.CharField(
        max_length=255,
        help_text="e.g. 10th Pass, 12th Pass, Any Graduate, Engineering Degree",
    )
    min_qualification = models.CharField(
        max_length=30,
        blank=True,
        choices=QUALIFICATION_CHOICES,
        help_text="Standardized qualification level required for eligibility matching (optional)",
    )
    location = models.CharField(
        max_length=255,
        default="All India",
        help_text="e.g. All India, Uttar Pradesh, Delhi, Bihar",
    )
    category = models.CharField(
        max_length=100,
        default="Central",
        blank=True,
        help_text="e.g. Central, State, Railway, Defence, Banking, Police, Teaching",
    )
    vacancies_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total number of vacancies, if announced by the authority",
    )

    # Eligibility & Age Criteria
    min_age = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum age requirement in complete years (e.g. 18)",
    )
    max_age = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum age limit in complete years for unreserved/general candidates (e.g. 27)",
    )
    age_cutoff_date = models.DateField(
        null=True,
        blank=True,
        help_text="Official cutoff date for age calculation (e.g. 2026-08-01). If unset, defaults to application deadline or current date.",
    )

    # Candidate date-of-birth window (inclusive boundaries)
    dob_start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Earliest eligible candidate date of birth (inclusive). This is a candidate DOB boundary, not the application opening date.",
    )
    dob_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Latest eligible candidate date of birth (inclusive). This is a candidate DOB boundary, not the application closing date.",
    )

    # Candidate qualifications accepted for this exam
    eligible_qualifications = models.ManyToManyField(
        Qualification,
        blank=True,
        related_name="jobs",
        help_text="One or more qualifications accepted for this exam. A candidate qualifies if their qualification matches any selected option.",
    )

    # Application dates
    application_start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Opening date for online applications",
    )
    application_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Last date for online applications",
    )

    # Official URLs and verification
    official_notification_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Official recruitment notification or advertisement PDF link",
    )
    application_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Official direct application portal link",
    )
    source_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Source URL on the official commission or department portal",
    )
    last_verified_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date when information was last verified against official government portal",
    )

    # Publication status and labels
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="published",
        help_text="Publication status: draft, published, or archived",
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="Flag indicating whether details are verified from official sources",
    )
    is_expired = models.BooleanField(
        default=False,
        help_text="Flag indicating whether this recruitment drive is closed or expired",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-application_end_date", "-created_at"]
        verbose_name = "Government Job"
        verbose_name_plural = "Government Jobs"
        indexes = [
            models.Index(fields=["status", "is_expired"]),
            models.Index(fields=["organization"]),
            models.Index(fields=["qualification"]),
            models.Index(fields=["location"]),
            models.Index(fields=["category"]),
            models.Index(fields=["min_age", "max_age"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.organization})"

    def clean(self):
        super().clean()
        if (
            self.dob_start_date
            and self.dob_end_date
            and self.dob_start_date > self.dob_end_date
        ):
            raise ValidationError(
                {
                    "dob_start_date": (
                        "DOB starting date cannot be later than the DOB ending date. "
                        "Set the earliest eligible date of birth on or before the latest one."
                    ),
                }
            )

    @property
    def is_active(self):
        if self.status != "published" or self.is_expired:
            return False
        if self.application_end_date and self.application_end_date < timezone.now().date():
            return False
        return True

    @property
    def has_age_criteria(self):
        """Returns True if the exam has configured age criteria."""
        return self.min_age is not None or self.max_age is not None

    @property
    def has_dob_criteria(self):
        """Returns True if the exam has a configured candidate DOB window."""
        return self.dob_start_date is not None or self.dob_end_date is not None

    @property
    def dob_criteria_display(self):
        """Formatted candidate DOB window (inclusive)."""
        if self.dob_start_date and self.dob_end_date:
            start = self.dob_start_date.strftime("%d %b %Y")
            end = self.dob_end_date.strftime("%d %b %Y")
            if self.dob_start_date == self.dob_end_date:
                return f"Born on {start} only"
            return f"Born between {start} and {end} (both inclusive)"
        if self.dob_start_date:
            return f"Born on or after {self.dob_start_date.strftime('%d %b %Y')}"
        if self.dob_end_date:
            return f"Born on or before {self.dob_end_date.strftime('%d %b %Y')}"
        return "Not configured"

    def get_effective_cutoff_date(self):
        """Return the effective cutoff date for age calculation."""
        if self.age_cutoff_date:
            return self.age_cutoff_date, "official"
        if self.application_end_date:
            return self.application_end_date, "application_deadline"
        return timezone.localdate(), "today"

    @property
    def age_criteria_display(self):
        """Formatted age criteria string."""
        if self.min_age is not None and self.max_age is not None:
            return f"{self.min_age} to {self.max_age} years"
        elif self.min_age is not None:
            return f"Minimum {self.min_age} years"
        elif self.max_age is not None:
            return f"Up to {self.max_age} years"
        return "Not configured"

    def to_dict(self):
        """Helper to serialize job object cleanly for API responses."""
        return {
            "id": self.id,
            "title": self.title,
            "organization": self.organization,
            "qualification": self.qualification,
            "min_qualification": self.min_qualification,
            "location": self.location,
            "category": self.category,
            "vacancies_count": self.vacancies_count,
            "min_age": self.min_age,
            "max_age": self.max_age,
            "age_cutoff_date": self.age_cutoff_date.isoformat() if self.age_cutoff_date else None,
            "dob_start_date": self.dob_start_date.isoformat() if self.dob_start_date else None,
            "dob_end_date": self.dob_end_date.isoformat() if self.dob_end_date else None,
            "eligible_qualifications": (
                list(self.eligible_qualifications.values_list("code", flat=True))
                if self.pk
                else []
            ),
            "application_start_date": self.application_start_date.isoformat() if self.application_start_date else None,
            "application_end_date": self.application_end_date.isoformat() if self.application_end_date else None,
            "official_notification_url": self.official_notification_url,
            "application_url": self.application_url,
            "source_url": self.source_url,
            "last_verified_date": self.last_verified_date.isoformat() if self.last_verified_date else None,
            "is_verified": self.is_verified,
            "is_expired": self.is_expired,
            "is_active": self.is_active,
        }


class JobAgeRelaxation(models.Model):
    class Category(models.TextChoices):
        OBC = "obc", "OBC (Other Backward Classes)"
        SC = "sc", "SC (Scheduled Caste)"
        ST = "st", "ST (Scheduled Tribe)"
        PWD = "pwd", "PwD (Persons with Disabilities)"
        EX_SERVICEMEN = "ex_servicemen", "Ex-Servicemen"
        EWS = "ews", "EWS (Economically Weaker Sections)"
        OTHER = "other", "Other"

    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name="age_relaxations",
    )
    category = models.CharField(max_length=40, choices=Category.choices)
    relaxation_years = models.PositiveIntegerField(
        help_text="Age relaxation in years above the general maximum age"
    )

    class Meta:
        unique_together = ("job", "category")
        verbose_name = "Age Relaxation Rule"
        verbose_name_plural = "Age Relaxation Rules"

    def __str__(self):
        return f"{self.job.title} - {self.get_category_display()}: +{self.relaxation_years} yrs"

