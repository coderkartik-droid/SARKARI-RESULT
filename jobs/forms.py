from datetime import date
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import QUALIFICATION_DEFINITIONS, Qualification


# Derived from QUALIFICATION_DEFINITIONS so the labels never drift from the
# qualification records seeded by migration 0004_seed_default_qualifications.
QUALIFICATION_CHOICES = [
    ("", "Any / Not specified"),
    *[(code, name) for code, name, _rank in QUALIFICATION_DEFINITIONS],
]

QUALIFICATION_PLACEHOLDER = "Select your qualification"


def qualification_choices():
    """Dropdown options built from the project's qualification records.

    Values are the qualification ``code`` (the stable identifier the shared
    eligibility engine compares against), never a duplicated ad-hoc list.
    """
    records = list(Qualification.objects.filter(is_active=True).order_by("rank", "name"))
    if records:
        options = [(record.code, record.name) for record in records]
    else:
        options = [(code, name) for code, name, _rank in QUALIFICATION_DEFINITIONS]
    return [("", QUALIFICATION_PLACEHOLDER), *options]


class EligibilityCheckForm(forms.Form):
    dob = forms.DateField(
        label="Date of Birth",
        required=True,
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "portal-form-input",
                "id": "id_dob",
                "placeholder": "YYYY-MM-DD",
            }
        ),
        error_messages={
            "required": "Please enter your date of birth.",
            "invalid": "Enter a valid date in YYYY-MM-DD format.",
        },
    )
    qualification = forms.ChoiceField(
        label="Your Qualification",
        choices=QUALIFICATION_CHOICES,
        required=True,
        widget=forms.Select(
            attrs={
                "class": "portal-form-select",
                "id": "id_qualification",
            }
        ),
        error_messages={
            "required": "Please select your qualification.",
            "invalid_choice": "Select a qualification from the list.",
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["qualification"].choices = qualification_choices()
        if not self.is_bound:
            self.fields["dob"].widget.attrs["aria-describedby"] = "dob-hint"
            self.fields["qualification"].widget.attrs["aria-describedby"] = "qualification-hint"

    def clean_dob(self):
        dob = self.cleaned_data.get("dob")
        if not dob:
            return dob

        today = timezone.localdate()
        if dob > today:
            raise ValidationError("Date of birth cannot be in the future.")

        min_reasonable_date = date(1920, 1, 1)
        if dob < min_reasonable_date:
            raise ValidationError("Please enter a valid date of birth (after 1920).")

        return dob

    def clean(self):
        cleaned_data = super().clean()
        if "dob" in self.errors:
            widget_attrs = self.fields["dob"].widget.attrs
            classes = set(widget_attrs.get("class", "portal-form-input").split())
            classes.add("is-invalid")
            widget_attrs["class"] = " ".join(sorted(classes))
            widget_attrs["aria-invalid"] = "true"
            widget_attrs["aria-describedby"] = "dob-error"
        else:
            widget_attrs = self.fields["dob"].widget.attrs
            classes = set(widget_attrs.get("class", "portal-form-input").split())
            classes.discard("is-invalid")
            widget_attrs["class"] = " ".join(sorted(classes))
            widget_attrs.pop("aria-invalid", None)
            widget_attrs["aria-describedby"] = "dob-hint"

        if "qualification" in self.errors:
            widget_attrs = self.fields["qualification"].widget.attrs
            classes = set(widget_attrs.get("class", "portal-form-select").split())
            classes.add("is-invalid")
            widget_attrs["class"] = " ".join(sorted(classes))
            widget_attrs["aria-invalid"] = "true"
            widget_attrs["aria-describedby"] = "qualification-error"
        else:
            widget_attrs = self.fields["qualification"].widget.attrs
            classes = set(widget_attrs.get("class", "portal-form-select").split())
            classes.discard("is-invalid")
            widget_attrs["class"] = " ".join(sorted(classes))
            widget_attrs.pop("aria-invalid", None)
            widget_attrs["aria-describedby"] = "qualification-hint"

        return cleaned_data
