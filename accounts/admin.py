from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.password_validation import validate_password

from .models import EmailUser


class EmailUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput,
    )

    class Meta:
        model = EmailUser
        fields = ("username", "email", "full_name")

    def clean_username(self):
        username = self.cleaned_data["username"].strip().casefold()
        if EmailUser.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already in use.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().casefold()
        if EmailUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email address is already in use.")
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("The passwords do not match.")
        if password2:
            validate_password(
                password2,
                user=EmailUser(
                    username=self.cleaned_data.get("username", ""),
                    email=self.cleaned_data.get("email", ""),
                    full_name=self.cleaned_data.get("full_name", ""),
                ),
            )
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            self.save_m2m()
        return user


class EmailUserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField()

    class Meta:
        model = EmailUser
        fields = "__all__"

    def clean_password(self):
        return self.initial["password"]


@admin.register(EmailUser)
class EmailUserAdmin(UserAdmin):
    add_form = EmailUserCreationForm
    form = EmailUserChangeForm
    model = EmailUser
    ordering = ("username",)
    list_display = ("username", "email", "is_staff", "is_active")
    search_fields = ("username", "email", "full_name")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    readonly_fields = ("last_login", "date_joined")
    fieldsets = (
        (None, {"fields": ("username", "email", "full_name", "password")}),
        (
            "Eligibility profile",
            {
                "fields": ("date_of_birth", "qualification"),
                "description": "Candidate details used by the exam eligibility checker.",
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "username",
                    "full_name",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )
    filter_horizontal = ("groups", "user_permissions")
