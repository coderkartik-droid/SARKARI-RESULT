from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect

from .google_utils import google_email_is_verified
from .models import EmailUser


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom allauth social account adapter that:
    1. Populates full_name and lowercases username/email for the custom EmailUser model.
    2. Safely connects existing accounts ONLY when the provider email is verified.
    3. Blocks unverified third-party emails from taking over existing accounts.
    4. Applies the application's safe login redirect rules.
    """

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)

        # Normalize username and email
        if user.username:
            user.username = user.username.strip().casefold()
        if user.email:
            user.email = user.email.strip().casefold()

        # Custom EmailUser requires full_name
        if not getattr(user, "full_name", None):
            name = (
                data.get("name")
                or f"{user.first_name} {user.last_name}".strip()
                or user.username
                or "User"
            )
            user.full_name = name[:150]

        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form=form)
        if not getattr(user, "full_name", None):
            user.full_name = user.username[:150]
            user.save(update_fields=["full_name"])
        return user

    def pre_social_login(self, request, sociallogin):
        # If social account is already linked to a user, proceed normally
        if sociallogin.is_existing:
            return

        # If user is already authenticated in session, linking is handled by allauth
        if request.user.is_authenticated:
            return

        # Extract email from the social account
        email = sociallogin.user.email
        if not email and sociallogin.account.extra_data:
            email = sociallogin.account.extra_data.get("email")

        if not email:
            messages.error(
                request,
                "Google did not provide an email address. Please sign in with your password.",
            )
            raise ImmediateHttpResponse(redirect("accounts:login"))

        email = email.strip().casefold()
        is_verified = any(
            email_record.email.strip().casefold() == email and email_record.verified
            for email_record in sociallogin.email_addresses
        )
        extra = sociallogin.account.extra_data or {}
        if not is_verified:
            is_verified = any(
                google_email_is_verified(extra.get(key))
                for key in ("email_verified", "verified_email")
            )

        if not is_verified:
            messages.error(
                request,
                "Google did not verify this email address. Please sign in with your password.",
            )
            raise ImmediateHttpResponse(redirect("accounts:login"))

        existing_user = EmailUser.objects.filter(email__iexact=email).first()
        if not existing_user:
            return

        # Email is verified: safely connect social account to existing user
        sociallogin.connect(request, existing_user)

    def get_login_redirect_url(self, request):
        from accounts.views import _login_redirect_url

        return _login_redirect_url(request, request.user)
