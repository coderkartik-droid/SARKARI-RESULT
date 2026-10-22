from django.contrib import admin
from django import forms

from .models import Job, JobAgeRelaxation, Qualification


class JobAgeRelaxationInline(admin.TabularInline):
    model = JobAgeRelaxation
    extra = 1


class JobAdminForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.required = (name == "title")
        for field_name in (
            "official_notification_url",
            "application_url",
            "source_url",
        ):
            self.fields[field_name].widget.attrs["data-test-link"] = "true"
            self.fields[field_name].widget.attrs["inputmode"] = "url"
        for field_name in ("dob_start_date", "dob_end_date"):
            # The admin renders these as date pickers; make the intent explicit.
            self.fields[field_name].widget.attrs["class"] = "vDateField"

    def clean(self):
        cleaned_data = super().clean()
        dob_start = cleaned_data.get("dob_start_date")
        dob_end = cleaned_data.get("dob_end_date")
        if dob_start and dob_end and dob_start > dob_end:
            self.add_error(
                "dob_start_date",
                "DOB starting date cannot be later than the DOB ending date.",
            )
        return cleaned_data


@admin.register(Qualification)
class QualificationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "rank", "is_active")
    list_editable = ("rank", "is_active")
    search_fields = ("name", "code")
    ordering = ("rank", "name")


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    class Media:
        js = ("site_management/management_link_test.js",)

    form = JobAdminForm
    list_display = (
        "title",
        "organization",
        "qualification",
        "min_qualification",
        "min_age",
        "max_age",
        "dob_start_date",
        "dob_end_date",
        "location",
        "category",
        "vacancies_count",
        "application_end_date",
        "status",
        "is_verified",
        "is_expired",
        "last_verified_date",
    )
    list_filter = (
        "status",
        "is_verified",
        "is_expired",
        "min_qualification",
        "eligible_qualifications",
        "category",
        "location",
    )
    search_fields = (
        "title",
        "organization",
        "qualification",
        "location",
        "category",
    )
    date_hierarchy = "application_end_date"
    list_editable = ("status", "is_verified", "is_expired")
    inlines = [JobAgeRelaxationInline]
    filter_horizontal = ("eligible_qualifications",)
    fieldsets = (
        (
            "Recruitment Details",
            {
                "fields": (
                    "title",
                    "organization",
                    "category",
                    "qualification",
                    "location",
                    "vacancies_count",
                )
            },
        ),
        (
            "Eligibility Criteria",
            {
                "fields": (
                    "min_age",
                    "max_age",
                    "age_cutoff_date",
                    "min_qualification",
                ),
                "description": "Optional age range and qualification criteria for candidate eligibility checking.",
            },
        ),
        (
            "Candidate Date of Birth & Qualifications",
            {
                "fields": (
                    "dob_start_date",
                    "dob_end_date",
                    "eligible_qualifications",
                ),
                "description": (
                    "Candidate date-of-birth window (both boundaries inclusive) and the "
                    "qualifications accepted for this exam. These fields drive the dynamic "
                    "eligibility check shown to users."
                ),
            },
        ),
        (
            "Application Schedule",
            {
                "fields": (
                    "application_start_date",
                    "application_end_date",
                )
            },
        ),
        (
            "Official Links & Verification",
            {
                "fields": (
                    "official_notification_url",
                    "application_url",
                    "source_url",
                    "last_verified_date",
                    "is_verified",
                )
            },
        ),
        (
            "Publication & Lifecycle",
            {
                "fields": (
                    "status",
                    "is_expired",
                )
            },
        ),
    )
