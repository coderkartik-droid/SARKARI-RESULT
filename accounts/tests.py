from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.cookie import CookieStorage
from django.contrib.auth.tokens import default_token_generator, PasswordResetTokenGenerator
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.html import escape
from django.utils.http import urlsafe_base64_encode

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from allauth.account.models import EmailAddress

from accounts.adapter import CustomSocialAccountAdapter
from accounts.backends import UsernameOrEmailBackend
from jobs.models import Job
from site_management.models import (
    ContentItem,
    ContentSection,
    Exam,
    ExamPDF,
    SocialMediaProfile,
    WebsitePage,
)


User = get_user_model()


def make_exam_pdf_upload(name="notice.pdf"):
    return SimpleUploadedFile(
        name,
        (
            b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
            b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
        ),
        content_type="application/pdf",
    )


class HomepageAnchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.fragments = []
        self.anchors = []
        self._current_anchor = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(attributes["id"])
        if tag == "a":
            href = attributes.get("href", "")
            self._current_anchor = {"href": href, "text": ""}
            self.anchors.append(self._current_anchor)
            if href.startswith("#") and len(href) > 1:
                self.fragments.append(href[1:])

    def handle_data(self, data):
        if self._current_anchor is not None:
            self._current_anchor["text"] += data

    def handle_endtag(self, tag):
        if tag == "a":
            self._current_anchor = None


class FooterSocialProfileTests(TestCase):
    def test_default_social_icons_render_without_configured_profiles(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        for url in (
            "https://www.instagram.com/",
            "https://www.whatsapp.com/",
            "https://www.facebook.com/",
        ):
            self.assertContains(response, f'href="{url}"')
        self.assertContains(response, 'rel="noopener noreferrer"')

    def test_saved_social_profile_url_is_used_in_footer(self):
        SocialMediaProfile.objects.create(
            platform=SocialMediaProfile.Platform.INSTAGRAM,
            profile_url="https://www.instagram.com/example/",
            built_in_icon="instagram",
            accessible_label="Instagram",
            display_location=SocialMediaProfile.DisplayLocation.FOOTER,
        )

        response = self.client.get(reverse("home"))

        self.assertContains(
            response,
            'href="https://www.instagram.com/example/"',
        )


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
class RegistrationTests(TestCase):
    def setUp(self):
        cache.clear()

    def registration_data(self, **overrides):
        data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "exampl3pass",
            "confirmPassword": "exampl3pass",
            "acceptTerms": "on",
        }
        data.update(overrides)
        return data

    def test_successful_registration_hashes_password_and_signs_in(self):
        response = self.client.post(
            reverse("accounts:signup"),
            self.registration_data(),
        )

        user = User.objects.get(email="test@example.com")
        self.assertRedirects(response, reverse("accounts:dashboard"))
        self.assertEqual(user.username, "testuser")
        self.assertEqual(user.full_name, "testuser")
        self.assertTrue(user.check_password("exampl3pass"))
        self.assertNotEqual(user.password, "exampl3pass")
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_duplicate_email_is_rejected_case_insensitively(self):
        User.objects.create_user(
            username="existinguser",
            email="test@example.com",
            password="exampl3pass",
        )

        response = self.client.post(
            reverse("accounts:signup"),
            self.registration_data(email="TEST@EXAMPLE.COM"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.count(), 1)

    def test_duplicate_username_is_rejected_case_insensitively(self):
        User.objects.create_user(
            username="existinguser",
            email="existing@example.com",
            password="exampl3pass",
        )

        response = self.client.post(
            reverse("accounts:signup"),
            self.registration_data(username="EXISTINGUSER"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This username is already taken.")
        self.assertEqual(User.objects.count(), 1)

    def test_invalid_email_is_rejected(self):
        response = self.client.post(
            reverse("accounts:signup"),
            self.registration_data(email="not-an-email"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid email address.")
        self.assertEqual(User.objects.count(), 0)

    def test_short_password_is_rejected(self):
        response = self.client.post(
            reverse("accounts:signup"),
            self.registration_data(password="a1", confirmPassword="a1"),
        )

        self.assertContains(
            response,
            "Password must contain at least 8 characters and one number.",
        )
        self.assertEqual(User.objects.count(), 0)

    def test_password_without_digit_is_rejected(self):
        response = self.client.post(
            reverse("accounts:signup"),
            self.registration_data(
                password="longpassword",
                confirmPassword="longpassword",
            ),
        )

        self.assertContains(
            response,
            "Password must contain at least 8 characters and one number.",
        )
        self.assertEqual(User.objects.count(), 0)

    def test_mismatched_passwords_are_rejected(self):
        response = self.client.post(
            reverse("accounts:signup"),
            self.registration_data(confirmPassword="different1"),
        )

        self.assertContains(response, "These passwords do not match.")
        self.assertEqual(User.objects.count(), 0)

    def test_missing_terms_acceptance_is_rejected(self):
        data = self.registration_data()
        del data["acceptTerms"]

        response = self.client.post(reverse("accounts:signup"), data)

        self.assertContains(
            response,
            "Accept the Terms and Privacy Policy to continue.",
        )
        self.assertEqual(User.objects.count(), 0)


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
class AuthenticationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password="exampl3pass",
        )

    def test_login_accepts_case_insensitive_username_and_redirects(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "TESTUSER", "password": "exampl3pass"},
        )

        self.assertRedirects(response, reverse("accounts:dashboard"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_accepts_case_insensitive_email_and_redirects(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "TEST@EXAMPLE.COM", "password": "exampl3pass"},
        )

        self.assertRedirects(response, reverse("accounts:dashboard"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_superuser_login_redirects_to_site_management(self):
        superuser = User.objects.create_superuser(
            username="siteadmin",
            email="siteadmin@example.com",
            full_name="Site Administrator",
            password="adminpass1",
        )

        response = self.client.post(
            reverse("accounts:login"),
            {"username": "siteadmin", "password": "adminpass1"},
        )

        self.assertRedirects(response, reverse("site_management:dashboard"))
        self.assertEqual(response.wsgi_request.user, superuser)
        self.assertContains(
            self.client.get(reverse("site_management:dashboard")),
            "Welcome, siteadmin!",
        )

    def test_superuser_cannot_be_redirected_to_normal_dashboard(self):
        User.objects.create_superuser(
            username="siteadmin",
            email="siteadmin@example.com",
            full_name="Site Administrator",
            password="adminpass1",
        )

        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "siteadmin",
                "password": "adminpass1",
                "next": reverse("accounts:dashboard"),
            },
        )

        self.assertRedirects(response, reverse("site_management:dashboard"))

    def test_superuser_visiting_user_dashboard_is_sent_to_site_management(self):
        User.objects.create_superuser(
            username="siteadmin",
            email="siteadmin@example.com",
            full_name="Site Administrator",
            password="adminpass1",
        )
        self.client.login(username="siteadmin", password="adminpass1")

        response = self.client.get(reverse("accounts:dashboard"))

        self.assertRedirects(response, reverse("site_management:dashboard"))

    def test_staff_user_keeps_normal_login_landing_and_cms_access(self):
        staff_user = User.objects.create_user(
            username="contentstaff",
            email="contentstaff@example.com",
            full_name="Content Staff",
            password="staffpass1",
            is_staff=True,
        )

        response = self.client.post(
            reverse("accounts:login"),
            {"username": "contentstaff", "password": "staffpass1"},
        )
        self.assertRedirects(response, reverse("accounts:dashboard"))

        self.client.logout()
        response = self.client.post(
            reverse("site_management:login"),
            {"username": "contentstaff", "password": "staffpass1"},
        )
        self.assertRedirects(response, reverse("site_management:dashboard"))
        self.assertEqual(response.wsgi_request.user, staff_user)

    def test_invalid_password_is_rejected_for_username_or_email(self):
        for identifier in ("testuser", "test@example.com"):
            self.client.logout()
            response = self.client.post(
                reverse("accounts:login"),
                {"username": identifier, "password": "incorrect1"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertContains(
                response,
                "Invalid username or email, or password.",
            )
            self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_ambiguous_username_and_email_identifier_is_rejected(self):
        User.objects.create_user(
            username="collision@example.com",
            email="first@example.com",
            password="firstpass1",
        )
        User.objects.create_user(
            username="seconduser",
            email="collision@example.com",
            password="secondpass1",
        )

        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "collision@example.com",
                "password": "firstpass1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Invalid username or email, or password.",
        )
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_duplicate_email_matches_are_rejected_by_authentication_backend(self):
        other_user = User.objects.create_user(
            username="otheruser",
            email="other@example.com",
            password="otherpass1",
        )
        with patch.object(
            User._default_manager,
            "filter",
            side_effect=[[], [self.user, other_user]],
        ):
            user = UsernameOrEmailBackend().authenticate(
                None,
                username="test@example.com",
                password="exampl3pass",
            )

        self.assertIsNone(user)

    def test_login_redirects_only_to_same_site_next_url(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "testuser",
                "password": "exampl3pass",
                "next": "/",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("home"))

        self.client.logout()
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "testuser",
                "password": "exampl3pass",
                "next": "https://attacker.example/",
            },
        )

        self.assertRedirects(response, reverse("accounts:dashboard"))

    def test_invalid_login_uses_generic_error(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "missing@example.com", "password": "incorrect1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username or email, or password.")
        self.assertNotContains(response, "No account")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_repeated_failed_logins_are_throttled_generically(self):
        for _ in range(5):
            response = self.client.post(
                reverse("accounts:login"),
                {"username": "testuser", "password": "wrong-password"},
            )

        response = self.client.post(
            reverse("accounts:login"),
            {"username": "testuser", "password": "exampl3pass"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username or email, or password.")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_invalidates_session(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("accounts:logout"))

        self.assertRedirects(response, reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_dashboard_requires_authentication(self):
        response = self.client.get(reverse("accounts:dashboard"))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('accounts:dashboard')}",
        )

    def test_login_and_dashboard_are_available_after_sign_in(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounts:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "testuser")
        self.assertContains(response, "Sign out")

    def test_public_header_actions_are_exclusive_and_menu_is_available(self):
        signed_out = self.client.get(reverse("home"))
        self.assertContains(signed_out, "Log in")
        self.assertContains(signed_out, "Create account")
        self.assertContains(signed_out, "Check Eligibility")
        self.assertContains(signed_out, 'id="public-navigation-menu"')
        self.assertContains(signed_out, 'aria-label="All site navigation"')
        self.assertNotIn('class="portal-menu-toggle"', signed_out.content.decode())
        self.assertContains(signed_out, f'href="{reverse("home")}"')
        self.assertNotContains(signed_out, "Sign out")

        self.client.force_login(self.user)
        signed_in = self.client.get(reverse("home"))
        self.assertContains(signed_in, "Sign out")
        self.assertContains(signed_in, reverse("accounts:logout"))
        self.assertContains(signed_in, 'name="csrfmiddlewaretoken"')
        self.assertNotContains(signed_in, 'class="portal-login-link"')
        self.assertNotContains(signed_in, 'class="portal-signup-link"')

    def test_custom_user_is_manageable_in_django_admin(self):
        admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            full_name="Admin User",
            password="adminpass1",
        )
        self.client.force_login(admin_user)

        changelist = self.client.get(
            reverse("admin:accounts_emailuser_changelist")
        )
        add_form = self.client.get(reverse("admin:accounts_emailuser_add"))

        self.assertEqual(changelist.status_code, 200)
        self.assertEqual(add_form.status_code, 200)


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
class CsrfTests(TestCase):
    def test_login_post_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("accounts:login"))

        response = client.post(
            reverse("accounts:login"),
            {"username": "testuser", "password": "exampl3pass"},
        )

        self.assertEqual(response.status_code, 403)

    def test_signup_post_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("accounts:signup"))

        response = client.post(
            reverse("accounts:signup"),
            {
                "username": "testuser",
                "email": "test@example.com",
                "password": "exampl3pass",
                "confirmPassword": "exampl3pass",
                "acceptTerms": "on",
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_logout_post_requires_csrf_token(self):
        user = User.objects.create_user(
            username="csrfuser",
            email="csrf@example.com",
            full_name="CSRF User",
            password="exampl3pass",
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)

        response = client.post(reverse("accounts:logout"))

        self.assertEqual(response.status_code, 403)


class PortalHomepageTests(TestCase):
    def test_authenticated_navigation_links_to_messages_contact_form(self):
        user = User.objects.create_user(
            username="messagesnav",
            email="messagesnav@example.com",
            password="unused-test-password",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Messages")
        self.assertContains(response, f'href="{reverse("contact_us")}"')

    def test_home_is_first_and_unique_with_empty_or_cms_navigation(self):
        ContentSection.objects.filter(
            area=ContentSection.Area.NAVIGATION,
        ).delete()

        for url in (reverse("home"), reverse("about_us")):
            with self.subTest(url=url):
                response = self.client.get(url)
                content = response.content.decode()
                desktop_menu = content.split(
                    '<div class="portal-menu-links">', 1
                )[1].split("</div>", 1)[0]
                mobile_menu = content.split(
                    '<nav class="portal-mobile-nav"', 1
                )[1].split(">", 1)[1].split("</nav>", 1)[0]
                self.assertTrue(
                    desktop_menu.lstrip().startswith(
                        f'<a href="{reverse("home")}"'
                    )
                )
                self.assertTrue(
                    mobile_menu.lstrip().startswith(
                        f'<a href="{reverse("home")}"'
                    )
                )

        nav_section = ContentSection.objects.create(
            area=ContentSection.Area.NAVIGATION,
            title="Main navigation",
            slug="main-navigation-test",
        )
        ContentItem.objects.create(
            section=nav_section,
            label="Home",
            url=reverse("home"),
        )
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        desktop_menu = content.split(
            '<div class="portal-menu-links">', 1
        )[1].split("</div>", 1)[0]
        self.assertEqual(desktop_menu.count(f'href="{reverse("home")}"'), 1)

    def test_public_header_shows_the_fixed_section_buttons_in_order(self):
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        desktop_menu = content.split('<div class="portal-menu-links">', 1)[1].split(
            "</div>", 1
        )[0]
        mobile_menu = (
            content.split('<nav class="portal-mobile-nav"', 1)[1]
            .split(">", 1)[1]
            .split("</nav>", 1)[0]
        )

        expected_links = [
            ("Home", reverse("home")),
            ("Exams", reverse("accounts:exams")),
            ("Results", reverse("accounts:results")),
            ("Tools", reverse("tools")),
            ("Admit Card", reverse("accounts:section_list", args=["admit-cards"])),
            (
                "Previous Year Papers",
                reverse("accounts:previous_papers"),
            ),
        ]

        for label, url in expected_links:
            with self.subTest(label=label):
                self.assertContains(response, label)
                self.assertIn(f'href="{url}"', desktop_menu)
                self.assertIn(f'href="{url}"', mobile_menu)

        positions = [desktop_menu.index(f'href="{url}"') for _label, url in expected_links]
        self.assertEqual(positions, sorted(positions))
        self.assertTrue(
            desktop_menu.lstrip().startswith(f'<a href="{reverse("home")}"')
        )
        self.assertTrue(
            mobile_menu.lstrip().startswith(f'<a href="{reverse("home")}"')
        )

    def test_public_templates_render_the_assistant_once_and_keep_it_private(self):
        section = ContentSection.objects.get(slug="results")
        item = ContentItem.objects.create(
            section=section,
            label="Assistant coverage result",
            body="Published details for the assistant coverage test.",
        )
        job = Job.objects.create(
            title="Assistant coverage recruitment",
            organization="Public Commission",
            qualification="Graduate",
            status="published",
            is_verified=True,
            is_expired=False,
        )
        WebsitePage.objects.update(is_published=True)
        user = User.objects.create_user(
            username="assistantcoverage",
            email="assistantcoverage@example.com",
            password="exampl3pass",
        )

        public_urls = [
            reverse("home"),
            reverse("accounts:login"),
            reverse("accounts:signup"),
            reverse("accounts:section_list", args=[section.slug]),
            reverse(
                "accounts:section_item_detail",
                args=[section.slug, item.pk],
            ),
            reverse("jobs:list"),
            reverse("jobs:detail", args=[job.pk]),
            reverse("about_us"),
            reverse("contact_us"),
            reverse("privacy_policy"),
            reverse("content_details"),
        ]
        for url in public_urls:
            with self.subTest(url=url):
                if url == reverse("contact_us"):
                    self.client.force_login(user)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.content.decode("utf-8").count(
                        'id="ai-assistant-widget"'
                    ),
                    1,
                )

        self.client.force_login(user)
        dashboard = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(
            dashboard.content.decode("utf-8").count(
                'id="ai-assistant-widget"'
            ),
            1,
        )

        for url in (
            reverse("site_management:login"),
            reverse("admin:login"),
            reverse("accounts:section_list", args=["missing-section"]),
        ):
            with self.subTest(private_or_error_url=url):
                response = self.client.get(url)
                self.assertNotIn(
                    'id="ai-assistant-widget"',
                    response.content.decode("utf-8"),
                )

    def test_shared_styles_disable_motion_when_reduced_motion_is_requested(self):
        css = (
            Path(__file__).parent
            / "static"
            / "accounts"
            / "public.css"
        ).read_text(encoding="utf-8")
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn("animation-duration: .01ms !important", css)
        self.assertIn("transition-duration: .01ms !important", css)
        self.assertIn("scroll-behavior: auto !important", css)

    def test_shared_footer_uses_public_routes_and_published_information_pages(self):
        WebsitePage.objects.update(is_published=False)
        WebsitePage.objects.update_or_create(
            page_type=WebsitePage.PageType.ABOUT_US,
            defaults={
                "title": "About us",
                "description": "About the public portal.",
                "is_published": True,
            },
        )
        WebsitePage.objects.update_or_create(
            page_type=WebsitePage.PageType.PRIVACY_POLICY,
            defaults={
                "title": "Privacy policy",
                "description": "Privacy information.",
                "is_published": False,
            },
        )

        homepage = self.client.get(reverse("home"))
        website_page = self.client.get(reverse("about_us"))

        for response in (homepage, website_page):
            footer_html = response.content.decode().split("<footer", 1)[1].split(
                "</footer>", 1
            )[0]
            self.assertNotIn("Useful information", footer_html)
            self.assertEqual(footer_html.count('class="portal-footer-column"'), 3)
            self.assertIn(reverse("home"), footer_html)
            self.assertNotIn("Latest Jobs", footer_html)
            self.assertIn(reverse("accounts:section_list", args=["results"]), footer_html)
            self.assertIn(reverse("about_us"), footer_html)
            self.assertNotIn(reverse("contact_us"), footer_html)
            self.assertIn(reverse("privacy_policy"), footer_html)
            self.assertIn(reverse("terms_and_conditions"), footer_html)
            self.assertNotIn(reverse("content_details"), footer_html)
            self.assertNotIn('href="#"', footer_html)

    def test_homepage_shows_empty_state_when_no_sections_are_published(self):
        ContentSection.objects.filter(
            area=ContentSection.Area.HOMEPAGE,
        ).delete()

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No public content has been published yet.")

    def test_homepage_and_listing_hide_contentless_cms_items(self):
        section = ContentSection.objects.get(slug="results")
        blank_item = ContentItem.objects.create(section=section)

        homepage = self.client.get(reverse("home"))
        listing = self.client.get(
            reverse("accounts:section_list", args=[section.slug])
        )
        detail = self.client.get(
            reverse(
                "accounts:section_item_detail",
                args=[section.slug, blank_item.pk],
            )
        )

        self.assertNotContains(
            homepage,
            reverse("accounts:section_item_detail", args=[section.slug, blank_item.pk]),
        )
        self.assertNotContains(listing, f'href="{reverse("accounts:section_item_detail", args=[section.slug, blank_item.pk])}"')
        self.assertEqual(detail.status_code, 404)
        self.assertContains(detail, "This page is currently unavailable.", status_code=404)

    def test_unlinked_navigation_labels_are_not_rendered_as_dead_links(self):
        nav_section = ContentSection.objects.get(slug="main-navigation")
        ContentItem.objects.create(section=nav_section, label="No destination")

        response = self.client.get(reverse("home"))
        parser = HomepageAnchors()
        parser.feed(response.content.decode())

        self.assertContains(response, "No destination")
        self.assertFalse(any(anchor["href"] == "#" for anchor in parser.anchors))

    def test_unpublished_announcement_is_not_rendered(self):
        announcements = ContentSection.objects.create(
            area=ContentSection.Area.ANNOUNCEMENTS,
            title="Scheduled announcements",
            slug="scheduled-announcements",
        )
        ContentItem.objects.create(
            section=announcements,
            label="Future announcement",
            publish_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.get(reverse("home"))

        self.assertNotContains(response, "Future announcement")

    def test_missing_and_unpublished_public_pages_use_a_safe_404(self):
        WebsitePage.objects.update_or_create(
            page_type=WebsitePage.PageType.ABOUT_US,
            defaults={
                "title": "Private draft page",
                "description": "Draft content must not be exposed.",
                "is_published": False,
            },
        )
        WebsitePage.objects.filter(
            page_type=WebsitePage.PageType.PRIVACY_POLICY,
        ).update(is_published=False)

        for url in (
            reverse("about_us"),
            reverse("privacy_policy"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 404)
                self.assertContains(
                    response,
                    "This page is currently unavailable.",
                    status_code=404,
                )
                self.assertNotContains(
                    response,
                    "Draft content must not be exposed.",
                    status_code=404,
                )

    def test_published_page_with_blank_optional_content_has_fallback(self):
        WebsitePage.objects.update_or_create(
            page_type=WebsitePage.PageType.ABOUT_US,
            defaults={
                "title": "About us",
                "description": "",
                "is_published": True,
            },
        )

        response = self.client.get(reverse("about_us"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Content for this page is not available right now.")

    def test_homepage_internal_fragment_links_have_targets(self):
        response = self.client.get(reverse("home"))
        parser = HomepageAnchors()
        parser.feed(response.content.decode())

        self.assertTrue(parser.fragments)
        self.assertEqual(
            sorted(set(parser.fragments) - parser.ids),
            [],
        )

    def test_homepage_hides_jobs_section_and_keeps_jobs_listing_available(self):
        job = Job.objects.create(
            title="Dedicated Jobs Page Listing",
            organization="Public Commission",
            qualification="Graduate",
            status="published",
            is_verified=True,
            is_expired=False,
        )
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your gateway to")
        self.assertContains(response, "Latest Results")
        self.assertContains(response, "Admit Cards")
        self.assertContains(response, "Answer Keys")
        self.assertContains(response, "Syllabus &amp; Exam Pattern")
        self.assertContains(response, "Previous Year Question Papers")
        self.assertContains(response, "Important Updates &amp; Notifications")
        self.assertContains(response, "CMS CONTENT")
        self.assertNotIn("jobs", [section["id"] for section in response.context["sections"]])
        self.assertNotContains(response, 'id="jobs"')
        for section in response.context["sections"]:
            self.assertLessEqual(len(section["items"]), 2)
        self.assertContains(response, reverse("accounts:login"))
        self.assertContains(response, reverse("accounts:signup"))
        self.assertContains(response, "instagram.com")

        jobs_page = self.client.get(reverse("jobs:list"))
        self.assertEqual(jobs_page.status_code, 200)
        self.assertContains(jobs_page, job.title)

    def test_homepage_exams_section_renders_published_exams_and_pdf_links(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                exam = Exam.objects.create(
                    title="UPSC Civil Services 2026",
                    description="Official notification and syllabus.",
                    status=Exam.Status.PUBLISHED,
                )
                pdf = ExamPDF.objects.create(
                    exam=exam,
                    display_name="Official Notification",
                    pdf_file=make_exam_pdf_upload("upsc-notification.pdf"),
                )
                external = ExamPDF.objects.create(
                    exam=exam,
                    display_name="Apply Online",
                    external_link="https://upsc.gov.in/apply",
                    link_text="Apply online",
                )
                Exam.objects.create(
                    title="Draft Internal Exam",
                    status=Exam.Status.DRAFT,
                )

                response = self.client.get(reverse("home"))
                pdf_url = pdf.pdf_file.url

        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        # The Exams section lives in the homepage body, not only in the header.
        self.assertIn('id="exams"', content)
        self.assertContains(response, "UPSC Civil Services 2026")
        self.assertContains(response, "Official notification and syllabus.")
        self.assertIn(f'href="{pdf_url}"', content)
        self.assertIn(escape(pdf.display_name), content)
        self.assertIn(f'href="{external.external_link}"', content)
        self.assertIn(escape(external.link_text), content)
        # Draft exams must never surface on the homepage.
        self.assertNotContains(response, "Draft Internal Exam")

    def test_homepage_exams_section_shows_a_clean_empty_state(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="exams"', response.content.decode())
        self.assertContains(response, "There are no published exams yet.")

    def test_homepage_quick_actions_show_four_cards_without_admit_cards(self):
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        quick_access = content.split('class="portal-quick-access"', 1)[1].split(
            "</section>", 1
        )[0]

        self.assertEqual(quick_access.count('class="portal-quick-card"'), 4)
        self.assertIn(f'href="{reverse("accounts:exams")}"', quick_access)
        self.assertNotIn(
            f'href="{reverse("accounts:section_list", args=["admit-cards"])}"',
            quick_access,
        )

        existing = [
            section
            for section in response.context["sections"][:4]
            if section["id"] != "admit-cards"
        ]
        self.assertEqual(len(existing), 3)
        for section in existing:
            with self.subTest(section=section["title"]):
                self.assertIn(f'href="{section["list_url"]}"', quick_access)

    def test_header_and_footer_category_links_open_their_listing_pages(self):
        response = self.client.get(reverse("home"))
        parser = HomepageAnchors()
        parser.feed(response.content.decode())

        category_routes = {
            "Results": reverse("accounts:section_list", args=["results"]),
            "Admit Cards": reverse("accounts:section_list", args=["admit-cards"]),
            "Answer Keys": reverse("accounts:section_list", args=["answer-keys"]),
        }
        for label, expected_url in category_routes.items():
            with self.subTest(category=label):
                self.assertTrue(
                    any(
                        expected_url == anchor["href"]
                        and label.casefold() in anchor["text"].casefold()
                        for anchor in parser.anchors
                    ),
                    f"{label} should link to {expected_url}",
                )
                self.assertEqual(self.client.get(expected_url).status_code, 200)

        nav_section = ContentSection.objects.get(slug="main-navigation")
        ContentItem.objects.create(
            section=nav_section,
            label="Admissions",
            url="#admissions",
            sort_order=70,
        )
        admissions_fallback = self.client.get(reverse("home"))
        nav_sections = admissions_fallback.context["navigation_sections"]
        self.assertTrue(
            any(
                item.label == "Admissions"
                and item.listing_url
                == reverse("accounts:section_list", args=["updates"])
                for section in nav_sections
                for item in section.items.all()
            )
        )
        parser = HomepageAnchors()
        parser.feed(admissions_fallback.content.decode())
        self.assertTrue(
            any(
                anchor["href"] == reverse("accounts:section_list", args=["updates"])
                and "Admissions" in anchor["text"]
                for anchor in parser.anchors
            )
        )
        self.assertEqual(
            self.client.get(reverse("accounts:section_list", args=["updates"])).status_code,
            200,
        )

    def test_homepage_category_cards_and_content_cards_use_listing_and_detail_urls(self):
        section = ContentSection.objects.get(slug="results")
        item = section.items.filter(is_active=True, parent__isnull=True).first()
        response = self.client.get(reverse("home"))
        parser = HomepageAnchors()
        parser.feed(response.content.decode())

        listing_url = reverse("accounts:section_list", args=["results"])
        detail_url = reverse(
            "accounts:section_item_detail",
            args=[section.slug, item.pk],
        )
        self.assertTrue(
            any(
                anchor["href"] == listing_url
                and "latest results" in anchor["text"].casefold()
                for anchor in parser.anchors
            )
        )
        self.assertTrue(
            any(
                anchor["href"] == detail_url
                and item.label in anchor["text"]
                for anchor in parser.anchors
            )
        )

    def test_search_filters_demo_sections_on_the_server(self):
        response = self.client.get(reverse("home"), {"q": "admit card"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["result_count"], 2)
        self.assertContains(response, "Sample admit card release update")
        results_section = next(
            section for section in response.context["sections"] if section["id"] == "results"
        )
        self.assertFalse(results_section["has_match"])
        self.assertFalse(results_section["items"][0]["matches_query"])
        self.assertRegex(
            response.content.decode(),
            r'<section[^>]*id="results"[^>]*\shidden[^>]*>',
        )
        self.assertContains(response, "matching “admit card”")

    def test_search_with_no_matches_shows_a_clear_empty_state(self):
        response = self.client.get(reverse("home"), {"q": "no-such-exam"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["result_count"], 0)
        self.assertContains(response, "No demo listings match")
        self.assertTrue(
            all(not section["has_match"] for section in response.context["sections"])
        )

    def test_cms_section_view_all_lists_latest_active_items_and_paginates(self):
        section = ContentSection.objects.get(slug="results")
        items = [
            ContentItem.objects.create(
                section=section,
                label=f"Result notice {number}",
                body="Published result information.",
            )
            for number in range(25)
        ]
        base_time = items[0].created_at
        for number, item in enumerate(items):
            ContentItem.objects.filter(pk=item.pk).update(
                created_at=base_time + timedelta(seconds=number)
            )
        inactive = ContentItem.objects.create(
            section=section,
            label="Restricted draft notice",
            is_active=False,
        )
        response = self.client.get(
            reverse("accounts:section_list", args=[section.slug])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 27)
        self.assertEqual(len(response.context["page_obj"].object_list), 20)
        self.assertEqual(response.context["page_obj"].object_list[0].pk, items[-1].pk)
        self.assertNotContains(response, "Restricted draft notice")

        second_page = self.client.get(
            reverse("accounts:section_list", args=[section.slug]),
            {"page": 2},
        )
        self.assertEqual(len(second_page.context["page_obj"].object_list), 7)
        self.assertEqual(
            second_page.context["page_obj"].object_list[0].pk,
            items[4].pk,
        )

        self.assertNotIn(inactive, second_page.context["page_obj"].object_list)

    def test_cms_listing_invalid_and_out_of_range_pages_are_handled(self):
        section = ContentSection.objects.get(slug="results")

        invalid = self.client.get(
            reverse("accounts:section_list", args=[section.slug]),
            {"page": "not-a-number"},
        )
        beyond = self.client.get(
            reverse("accounts:section_list", args=[section.slug]),
            {"page": "999"},
        )

        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(invalid.context["page_obj"].number, 1)
        self.assertEqual(beyond.status_code, 200)
        self.assertEqual(
            beyond.context["page_obj"].number,
            beyond.context["page_obj"].paginator.num_pages,
        )

    def test_homepage_cms_sections_show_two_latest_items(self):
        section = ContentSection.objects.get(slug="results")
        items = [
            ContentItem.objects.create(
                section=section,
                label=f"Homepage result {number}",
                body="Latest published result.",
            )
            for number in range(3)
        ]
        base_time = items[0].created_at
        for number, item in enumerate(items):
            ContentItem.objects.filter(pk=item.pk).update(
                created_at=base_time + timedelta(seconds=number)
            )

        response = self.client.get(reverse("home"))
        results_section = next(
            section for section in response.context["sections"] if section["id"] == "results"
        )

        self.assertEqual(len(results_section["items"]), 2)
        self.assertEqual(
            [item["id"] for item in results_section["items"]],
            [items[-1].pk, items[-2].pk],
        )
        self.assertEqual(
            results_section["list_url"],
            reverse("accounts:section_list", args=["results"]),
        )

    def test_empty_cms_category_has_a_helpful_empty_state(self):
        section = ContentSection.objects.create(
            area=ContentSection.Area.HOMEPAGE,
            title="Empty category",
            slug="empty-category",
        )

        response = self.client.get(
            reverse("accounts:section_list", args=[section.slug])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "There are no published items in this section yet.")

    def test_cms_listing_and_detail_hide_inactive_content(self):
        section = ContentSection.objects.get(slug="results")
        inactive_item = ContentItem.objects.create(
            section=section,
            label="Inactive private result",
            is_active=False,
        )
        inactive_section = ContentSection.objects.create(
            area=ContentSection.Area.HOMEPAGE,
            title="Hidden category",
            slug="hidden-category",
            is_active=False,
        )
        hidden_item = ContentItem.objects.create(
            section=inactive_section,
            label="Hidden item",
        )

        self.assertEqual(
            self.client.get(
                reverse("accounts:section_list", args=[inactive_section.slug])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse(
                    "accounts:section_item_detail",
                    args=[section.slug, inactive_item.pk],
                )
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse(
                    "accounts:section_item_detail",
                    args=[inactive_section.slug, hidden_item.pk],
                )
            ).status_code,
            404,
        )

    def test_cms_listing_cards_are_full_record_detail_links(self):
        section = ContentSection.objects.get(slug="results")
        item = ContentItem.objects.create(
            section=section,
            label="Clickable result record",
            body="Published result details.",
        )

        response = self.client.get(
            reverse("accounts:section_list", args=[section.slug])
        )

        self.assertContains(
            response,
            (
                f'class="portal-listing-card portal-listing-card-page '
                f'portal-card-main portal-full-card-link" '
                f'href="{reverse("accounts:section_item_detail", args=[section.slug, item.pk])}"'
            ),
        )

    def test_authenticated_homepage_shows_account_state_without_redirecting(self):
        user = User.objects.create_user(
            username="portaluser",
            email="portal@example.com",
            full_name="Portal User",
            password="exampl3pass",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Signed in as")
        self.assertContains(response, "portaluser")
        self.assertContains(response, reverse("accounts:dashboard"))
        self.assertContains(response, reverse("accounts:logout"))


class ExpiredTokenGenerator(PasswordResetTokenGenerator):
    def _now(self):
        return datetime.now() - timedelta(days=2)


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
class PasswordResetWorkflowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="resetuser",
            email="reset@example.com",
            full_name="Reset User",
            password="exampl3pass",
        )

    def test_login_page_renders_forgot_password_link_and_google_form(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("accounts:password_reset"))
        self.assertContains(response, reverse("accounts:google_login"))
        self.assertContains(response, 'data-forgot')
        self.assertContains(response, 'data-google-auth')

    def test_password_reset_form_renders_with_csrf_and_clean_layout(self):
        response = self.client.get(reverse("accounts:password_reset"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Forgot your")
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'name="email"')
        self.assertContains(response, 'class="auth-card reset-card"')
        self.assertNotContains(response, 'class="forms-viewport"')

    def test_password_reset_with_unknown_email_does_not_reveal_registration(self):
        mail.outbox.clear()
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "nonexistent@example.com"},
        )
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_with_registered_email_sends_email(self):
        mail.outbox.clear()
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "reset@example.com"},
        )
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertIn("Reset your password", sent_email.subject)
        self.assertIn(self.user.email, sent_email.body)
        self.assertIn("/accounts/password-reset/confirm/", sent_email.body)

    def test_password_reset_confirm_with_valid_token_updates_password(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        confirm_url = reverse(
            "accounts:password_reset_confirm",
            kwargs={"uidb64": uidb64, "token": token},
        )

        response = self.client.get(confirm_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["validlink"])
        self.assertContains(response, "Set new")

        post_response = self.client.post(
            response.request["PATH_INFO"],
            {
                "new_password1": "brandnewpass99",
                "new_password2": "brandnewpass99",
            },
        )
        self.assertRedirects(post_response, reverse("accounts:password_reset_complete"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brandnewpass99"))
        self.assertFalse(self.user.check_password("exampl3pass"))

    def test_password_reset_confirm_rejects_weak_password(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        confirm_url = reverse(
            "accounts:password_reset_confirm",
            kwargs={"uidb64": uidb64, "token": token},
        )

        response = self.client.get(confirm_url, follow=True)
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            response.request["PATH_INFO"],
            {
                "new_password1": "weak",
                "new_password2": "weak",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Password must contain at least 8 characters and one number.",
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("exampl3pass"))

    def test_password_reset_confirm_with_invalid_token_is_rejected(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        confirm_url = reverse(
            "accounts:password_reset_confirm",
            kwargs={"uidb64": uidb64, "token": "invalid-token-123"},
        )

        response = self.client.get(confirm_url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["validlink"])
        self.assertContains(response, "Invalid")

    def test_password_reset_confirm_with_expired_token_is_rejected(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        expired_token = ExpiredTokenGenerator().make_token(self.user)
        confirm_url = reverse(
            "accounts:password_reset_confirm",
            kwargs={"uidb64": uidb64, "token": expired_token},
        )

        response = self.client.get(confirm_url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["validlink"])
        self.assertContains(response, "Invalid")

    def test_password_reset_complete_page_renders_link_to_login(self):
        response = self.client.get(reverse("accounts:password_reset_complete"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Password")
        self.assertContains(response, reverse("accounts:login"))


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
class GoogleOAuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID="",
        GOOGLE_OAUTH_CLIENT_SECRET="",
        SOCIALACCOUNT_PROVIDERS={"google": {"APPS": []}},
    )
    def test_google_login_when_unconfigured_redirects_with_message(self):
        response = self.client.post(reverse("accounts:google_login"), follow=True)
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertContains(response, "Google sign-in is not configured yet")

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID="mock-google-client-id",
        GOOGLE_OAUTH_CLIENT_SECRET="mock-google-client-secret",
        SOCIALACCOUNT_PROVIDERS={
            "google": {
                "APPS": [
                    {
                        "client_id": "mock-google-client-id",
                        "secret": "mock-google-client-secret",
                        "key": "",
                    }
                ],
                "SCOPE": ["profile", "email"],
                "AUTH_PARAMS": {"access_type": "online"},
            }
        },
    )
    def test_google_login_initiates_oauth_redirect_when_configured(self):
        response = self.client.post(reverse("accounts:google_login"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("accounts.google.com/o/oauth2/v2/auth", response.url)
        self.assertIn("client_id=mock-google-client-id", response.url)

    def test_adapter_populates_custom_emailuser_fields(self):
        adapter = CustomSocialAccountAdapter()
        request = self.rf.get("/accounts/google/login/")
        sociallogin = SocialLogin()
        sociallogin.user = User()
        data = {
            "username": "OAuthUser",
            "email": "OAuthUser@Example.Com",
            "name": "Jane Google Doe",
        }

        user = adapter.populate_user(request, sociallogin, data)
        self.assertEqual(user.username, "oauthuser")
        self.assertEqual(user.email, "oauthuser@example.com")
        self.assertEqual(user.full_name, "Jane Google Doe")

    def test_adapter_links_existing_user_when_email_verified(self):
        existing_user = User.objects.create_user(
            username="existingalice",
            email="alice@example.com",
            full_name="Alice Existing",
            password="exampl3pass",
        )
        adapter = CustomSocialAccountAdapter()
        request = self.rf.get("/accounts/google/login/")
        request.user = AnonymousUser()
        request._messages = CookieStorage(request)

        social_account = SocialAccount(provider="google", uid="google-uid-123")
        sociallogin = SocialLogin(account=social_account)
        sociallogin.user = User(email="alice@example.com")
        sociallogin.email_addresses = [
            EmailAddress(email="alice@example.com", verified=True, primary=True)
        ]

        # `connect()` needs a provider app; supply one via settings so the
        # test does not depend on local .env OAuth credentials.
        with override_settings(
            SOCIALACCOUNT_PROVIDERS={
                "google": {
                    "APPS": [
                        {
                            "client_id": "mock-google-client-id",
                            "secret": "mock-google-client-secret",
                            "key": "",
                        }
                    ]
                }
            }
        ):
            adapter.pre_social_login(request, sociallogin)
        self.assertTrue(sociallogin.is_existing)
        self.assertEqual(sociallogin.user.pk, existing_user.pk)

    def test_adapter_strictly_blocks_linking_when_email_unverified(self):
        existing_user = User.objects.create_user(
            username="targetuser",
            email="target@example.com",
            full_name="Target User",
            password="exampl3pass",
        )
        adapter = CustomSocialAccountAdapter()
        request = self.rf.get("/accounts/google/login/")
        request.user = AnonymousUser()
        request._messages = CookieStorage(request)

        social_account = SocialAccount(provider="google", uid="attacker-uid-999")
        sociallogin = SocialLogin(account=social_account)
        sociallogin.user = User(email="target@example.com")
        sociallogin.email_addresses = [
            EmailAddress(email="target@example.com", verified=False, primary=True)
        ]

        with self.assertRaises(ImmediateHttpResponse) as cm:
            adapter.pre_social_login(request, sociallogin)

        self.assertEqual(cm.exception.response.status_code, 302)
        self.assertFalse(sociallogin.is_existing)

    def test_adapter_blocks_signup_with_unverified_google_email(self):
        adapter = CustomSocialAccountAdapter()
        request = self.rf.get("/accounts/google/login/")
        request.user = AnonymousUser()
        request._messages = CookieStorage(request)
        sociallogin = SocialLogin(
            account=SocialAccount(
                provider="google",
                uid="unverified-google-uid",
                extra_data={
                    "email": "new-user@example.com",
                    "email_verified": False,
                },
            )
        )
        sociallogin.user = User(email="new-user@example.com")

        with self.assertRaises(ImmediateHttpResponse) as cm:
            adapter.pre_social_login(request, sociallogin)

        self.assertEqual(cm.exception.response.status_code, 302)
        self.assertFalse(User.objects.filter(email="new-user@example.com").exists())

    def test_adapter_accepts_string_verified_google_claim(self):
        adapter = CustomSocialAccountAdapter()
        request = self.rf.get("/accounts/google/login/")
        request.user = AnonymousUser()
        request._messages = CookieStorage(request)
        sociallogin = SocialLogin(
            account=SocialAccount(
                provider="google",
                uid="verified-google-uid",
                extra_data={
                    "email": "new-user@example.com",
                    "email_verified": "true",
                },
            )
        )
        sociallogin.user = User(email="new-user@example.com")

        adapter.pre_social_login(request, sociallogin)

        self.assertFalse(User.objects.filter(email="new-user@example.com").exists())

    def test_adapter_get_login_redirect_url_respects_safe_redirect(self):
        user = User.objects.create_user(
            username="redirectuser",
            email="redirect@example.com",
            password="exampl3pass",
        )
        adapter = CustomSocialAccountAdapter()
        request = self.rf.get("/accounts/login/?next=/accounts/dashboard/")
        request.user = user

        redirect_url = adapter.get_login_redirect_url(request)
        self.assertEqual(redirect_url, reverse("accounts:dashboard"))
