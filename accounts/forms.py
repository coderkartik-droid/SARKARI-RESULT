from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import EmailUser


class SignupForm(forms.Form):
    username = forms.CharField(max_length=150, strip=True)
    email = forms.EmailField(max_length=254)
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput,
    )
    confirmPassword = forms.CharField(
        strip=False,
        widget=forms.PasswordInput,
    )
    acceptTerms = forms.BooleanField(
        required=True,
        error_messages={
            "required": "Accept the Terms and Privacy Policy to continue."
        },
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip().casefold()
        username_field = EmailUser._meta.get_field("username")
        for validator in username_field.validators:
            validator(username)
        if EmailUser.objects.filter(username__iexact=username).exists():
            raise ValidationError("This username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().casefold()
        if EmailUser.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "An account with this email address already exists."
            )
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        user = EmailUser(
            username=self.cleaned_data.get("username", ""),
            email=self.cleaned_data.get("email", ""),
            full_name=self.cleaned_data.get("username", ""),
        )
        try:
            password_validation.validate_password(password, user=user)
        except ValidationError as error:
            raise ValidationError(error.messages) from error
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirmation = cleaned_data.get("confirmPassword")
        if password and confirmation and password != confirmation:
            self.add_error("confirmPassword", "These passwords do not match.")
        return cleaned_data


class ProfileForm(forms.ModelForm):
    """Candidate details used by the exam eligibility checker."""

    class Meta:
        model = EmailUser
        fields = ["date_of_birth", "qualification"]
        labels = {
            "date_of_birth": "Date of birth",
            "qualification": "Highest qualification",
        }
        widgets = {
            "date_of_birth": forms.DateInput(
                attrs={"type": "date", "class": "portal-form-input"}
            ),
            "qualification": forms.Select(attrs={"class": "portal-form-select"}),
        }

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get("date_of_birth")
        if dob and dob > timezone.localdate():
            raise ValidationError("Date of birth cannot be in the future.")
        return dob
