from datetime import timedelta
from io import BytesIO
import os
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .models import (
    AnswerSheet,
    ContactSubmission,
    ContentItem,
    ContentLink,
    ContentSection,
    Exam,
    ExamPDF,
    PreviousPaper,
    RegistrationResource,
    ResourceURL,
    Result,
    WebsitePage,
    WebsiteSettings,
)


User = get_user_model()


def make_png_upload(name, color="navy"):
    image_bytes = BytesIO()
    Image.new("RGB", (8, 8), color=color).save(image_bytes, format="PNG")
    return SimpleUploadedFile(name, image_bytes.getvalue(), content_type="image/png")


def make_image_upload(name, image_format, color="navy"):
    image_bytes = BytesIO()
    Image.new("RGB", (8, 8), color=color).save(image_bytes, format=image_format)
    return SimpleUploadedFile(
        name,
        image_bytes.getvalue(),
        content_type="application/octet-stream",
    )


def make_pdf_upload(name="notice.pdf", content=None):
    if content is None:
        content = (
            b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
            b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
        )
    return SimpleUploadedFile(name, content, content_type="application/pdf")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SiteManagementTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser(
            username="cmsadmin",
            email="cmsadmin@example.com",
            password="Strongpass123",
        )
        self.member = User.objects.create_user(
            username="cmsmember",
            email="cmsmember@example.com",
            password="Strongpass123",
        )

    def test_anonymous_users_are_redirected_to_private_management_login(self):
        response = self.client.get(reverse("site_management:dashboard"))

        self.assertRedirects(
            response,
            f"{reverse('site_management:login')}?next={reverse('site_management:dashboard')}",
        )

    def test_all_management_mutations_require_staff_and_post(self):
        for url in (
            reverse("site_management:settings"),
            reverse("site_management:section_create"),
            reverse("site_management:item_create", args=[1]),
        ):
            response = self.client.post(url, {})
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("site_management:login"), response["Location"])

        self.client.force_login(self.staff)
        response = self.client.get(reverse("site_management:logout"))
        self.assertEqual(response.status_code, 405)

    def test_management_logout_clears_session(self):
        self.client.force_login(self.staff)

        response = self.client.post(reverse("site_management:logout"))

        self.assertRedirects(response, reverse("site_management:login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_non_staff_cannot_log_in_or_view_dashboard(self):
        response = self.client.post(
            reverse("site_management:login"),
            {"username": "cmsmember", "password": "Strongpass123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not authorized")
        self.assertNotIn("_auth_user_id", self.client.session)

        self.client.force_login(self.member)
        response = self.client.get(reverse("site_management:dashboard"))
        self.assertRedirects(
            response,
            f"{reverse('site_management:login')}?next={reverse('site_management:dashboard')}",
        )

    def test_normal_user_cannot_access_cms_settings_or_create_content(self):
        self.client.force_login(self.member)
        section = ContentSection.objects.create(
            area=ContentSection.Area.NAVIGATION,
            title="Test navigation",
            slug="test-navigation",
        )

        for url in (
            reverse("site_management:dashboard"),
            reverse("site_management:settings"),
            reverse("site_management:section_create"),
            reverse("site_management:item_create", args=[section.pk]),
        ):
            response = self.client.get(url)
            self.assertRedirects(
                response,
                f"{reverse('site_management:login')}?next={url}",
            )

    def test_staff_can_log_in_and_is_redirected_to_dashboard(self):
        response = self.client.post(
            reverse("site_management:login"),
            {"username": "cmsadmin", "password": "Strongpass123"},
        )

        self.assertRedirects(response, reverse("site_management:dashboard"))
        self.assertEqual(response.wsgi_request.user, self.staff)
        self.assertEqual(
            self.client.get(reverse("site_management:dashboard")).status_code,
            200,
        )

    def test_csrf_protects_management_login_and_content_changes(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.get(reverse("site_management:login"))
        response = client.post(
            reverse("site_management:login"),
            {"username": "cmsadmin", "password": "Strongpass123"},
        )
        self.assertEqual(response.status_code, 403)

        client.force_login(self.staff)
        response = client.post(reverse("site_management:settings"), {})
        self.assertEqual(response.status_code, 403)

    def test_public_pages_are_available_and_footer_has_single_privacy_link(self):
        self.assertEqual(self.client.get(reverse("about_us")).status_code, 200)
        self.assertEqual(self.client.get(reverse("privacy_policy")).status_code, 200)
        self.assertEqual(self.client.get(reverse("content_details")).status_code, 200)
        contact_response = self.client.get(reverse("contact_us"))
        self.assertRedirects(
            contact_response,
            f"{reverse('accounts:login')}?next={reverse('contact_us')}",
        )

        self.assertEqual(
            ContentItem.objects.filter(section__area=ContentSection.Area.FOOTER, label="Privacy Policy").count(),
            1,
        )

        privacy_response = self.client.get(reverse("privacy_policy"))
        self.assertContains(privacy_response, 'href="/privacy-policy/"')
        self.assertEqual(privacy_response.content.decode("utf-8").count('href="/privacy-policy/"'), 1)

    def test_contact_page_renders_and_saves_valid_submissions(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("contact_us"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="name"')
        self.assertContains(response, 'name="phone_number"')
        self.assertContains(response, 'name="email"')
        self.assertContains(response, 'name="message"')
        page_content = response.content.decode()
        self.assertLess(
            page_content.index('name="name"'),
            page_content.index('name="phone_number"'),
        )

        response = self.client.post(
            reverse("contact_us"),
            {
                "name": "  Applicant  ",
                "phone_number": "+91 98765 43210",
                "email": "applicant@example.com",
                "subject": "Question",
                "message": "Please help with this question.",
                "website": "",
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("contact_us"))
        self.assertContains(response, "Your message has been sent.")
        self.assertEqual(ContactSubmission.objects.count(), 1)
        submission = ContactSubmission.objects.get()
        self.assertEqual(submission.name, "Applicant")
        self.assertEqual(submission.phone_number, "+91 98765 43210")
        self.assertEqual(submission.email, "applicant@example.com")

        self.client.force_login(self.staff)
        inbox = self.client.get(
            reverse("admin:site_management_contactsubmission_changelist")
        )
        self.assertEqual(inbox.status_code, 200)
        self.assertContains(inbox, "Applicant")

    def test_logged_out_user_cannot_submit_contact_message(self):
        response = self.client.post(
            reverse("contact_us"),
            {
                "name": "Applicant",
                "phone_number": "9876543210",
                "email": "applicant@example.com",
                "subject": "Question",
                "message": "Please help with this question.",
                "website": "",
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('contact_us')}",
        )
        self.assertEqual(ContactSubmission.objects.count(), 0)

    def test_contact_form_rejects_honeypot_and_invalid_messages(self):
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("contact_us"),
            {
                "name": "Bot",
                "phone_number": "9876543210",
                "email": "bot@example.com",
                "subject": "Spam",
                "message": "Please visit https://example.com",
                "website": "filled-by-bot",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This form could not be submitted.")
        self.assertEqual(ContactSubmission.objects.count(), 0)

    def test_contact_form_rejects_invalid_phone_number(self):
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("contact_us"),
            {
                "name": "Applicant",
                "phone_number": "123",
                "email": "applicant@example.com",
                "subject": "Question",
                "message": "Please help with this question.",
                "website": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "7 to 15 digits")
        self.assertEqual(ContactSubmission.objects.count(), 0)

    def test_authorized_staff_can_list_and_open_contact_messages(self):
        self.client.force_login(self.staff)
        empty_response = self.client.get(reverse("site_management:contact_messages"))
        self.assertContains(empty_response, "No messages yet.")

        older = ContactSubmission.objects.create(
            name="Older sender",
            phone_number="9876543210",
            email="older@example.com",
            subject="Earlier question",
            message="Earlier message body.",
        )
        newer = ContactSubmission.objects.create(
            name="Newer sender",
            phone_number="+91 98765 43211",
            email="newer@example.com",
            subject="Latest question",
            message="<script>alert('unsafe')</script> Latest full message body.",
        )

        response = self.client.get(reverse("site_management:contact_messages"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Newer sender")
        self.assertContains(response, "+91 98765 43211")
        self.assertContains(response, "newer@example.com")
        self.assertLess(
            response.content.decode().index("Newer sender"),
            response.content.decode().index("Older sender"),
        )

        detail = self.client.get(
            reverse("site_management:contact_message_detail", args=[newer.pk])
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "&lt;script&gt;")
        self.assertNotContains(detail, "<script>")
        self.assertContains(detail, "Latest full message body.")
        self.assertEqual(
            self.client.get(
                reverse("site_management:contact_message_detail", args=[older.pk])
            ).status_code,
            200,
        )

    def test_staff_user_without_superuser_status_can_access_messages(self):
        staff_user = User.objects.create_user(
            username="message_staff",
            email="message_staff@example.com",
            password="Strongpass123",
        )
        staff_user.is_staff = True
        staff_user.save(update_fields=["is_staff"])
        self.client.force_login(staff_user)

        response = self.client.get(reverse("site_management:contact_messages"))

        self.assertEqual(response.status_code, 200)

    def test_contact_message_urls_reject_anonymous_and_non_staff_users(self):
        submission = ContactSubmission.objects.create(
            name="Private sender",
            phone_number="9876543210",
            email="private@example.com",
            subject="Private",
            message="This message is visible only to staff.",
        )
        urls = (
            reverse("site_management:contact_messages"),
            reverse("site_management:contact_message_detail", args=[submission.pk]),
        )
        for url in urls:
            with self.subTest(url=url):
                anonymous = self.client.get(url)
                self.assertEqual(anonymous.status_code, 302)
                self.assertIn(reverse("site_management:login"), anonymous["Location"])

                self.client.force_login(self.member)
                denied = self.client.get(url, follow=True)
                self.assertEqual(denied.status_code, 200)
                self.assertIn(
                    reverse("site_management:login"),
                    denied.redirect_chain[0][0],
                )
                self.assertNotContains(denied, "This message is visible only to staff.")
                self.client.logout()

    def test_logged_in_navigation_shows_message_link_only_to_signed_in_users(self):
        anonymous = self.client.get(reverse("home"))
        self.assertNotContains(anonymous, 'class="portal-login-link portal-message-link"')

        self.client.force_login(self.member)
        signed_in = self.client.get(reverse("home"))
        self.assertContains(
            signed_in,
            f'class="portal-login-link portal-message-link" href="{reverse("contact_us")}"',
        )

    def test_staff_can_edit_website_page_contact_details(self):
        page = WebsitePage.objects.get(page_type=WebsitePage.PageType.CONTACT_US)
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("site_management:website_page_edit", args=[page.pk]),
            {
                "title": "Contact",
                "subtitle": "Get in touch",
                "description": "Contact details and form.",
                "contact_email": "support@example.com",
                "contact_phone": "+91 1234567890",
                "contact_address": "New Delhi",
                "contact_hours": "Weekdays",
                "contact_intro": "Send us a message.",
                "contact_facebook_url": "https://facebook.com/example",
                "contact_instagram_url": "https://instagram.com/example",
                "contact_whatsapp_url": "https://wa.me/911234567890",
                "is_published": "on",
            },
        )

        self.assertRedirects(response, reverse("site_management:website_pages"))
        page.refresh_from_db()
        self.assertEqual(page.contact_email, "support@example.com")
        self.assertEqual(page.contact_phone, "+91 1234567890")
        self.assertEqual(page.contact_intro, "Send us a message.")

    def test_section_slug_suggestions_allow_saving_a_selected_slug(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("site_management:section_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<option value="admissions" label="Admissions"></option>',
            html=True,
        )

        response = self.client.post(
            reverse("site_management:section_create"),
            {
                "area": ContentSection.Area.HOMEPAGE,
                "title": "Admissions",
                "slug": "admissions",
                "description": "Admissions notices and application updates.",
                "sort_order": 0,
                "is_active": "on",
            },
        )
        self.assertRedirects(
            response,
            reverse("site_management:area_manager", args=[ContentSection.Area.HOMEPAGE]),
        )
        self.assertTrue(ContentSection.objects.filter(slug="admissions").exists())

    def test_page_create_requires_selecting_an_available_public_route(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("site_management:website_page_create"))
        self.assertEqual(response.status_code, 200)
        choices = response.context["form"].fields["page_type"].choices
        self.assertEqual(choices[0], ("", "Select a public page"))
        self.assertIn(
            (WebsitePage.PageType.TERMS_AND_CONDITIONS, "Terms and Conditions"),
            list(choices),
        )

        response = self.client.post(
            reverse("site_management:website_page_create"),
            {
                "page_type": WebsitePage.PageType.TERMS_AND_CONDITIONS,
                "title": "Terms and Conditions",
                "description": "Terms for using the website.",
                "is_published": "on",
            },
        )
        self.assertRedirects(response, reverse("site_management:website_pages"))
        self.assertTrue(
            WebsitePage.objects.filter(
                page_type=WebsitePage.PageType.TERMS_AND_CONDITIONS,
                title="Terms and Conditions",
            ).exists()
        )

    def test_cms_icon_picker_and_image_upload_fields_render(self):
        self.client.force_login(self.staff)

        section_response = self.client.get(reverse("site_management:section_create"))
        self.assertEqual(section_response.status_code, 200)
        self.assertContains(section_response, "management-icon-picker")
        self.assertContains(section_response, 'name="icon"')
        self.assertContains(section_response, "Phone")
        self.assertContains(
            section_response,
            "/static/site_management/management_icon_picker.css",
        )
        self.assertContains(
            section_response,
            "/static/site_management/management_icon_picker.js",
        )
        self.assertContains(section_response, '<option value="phone">Phone</option>')

        create_response = self.client.post(
            reverse("site_management:section_create"),
            {
                "area": ContentSection.Area.HOMEPAGE,
                "title": "Phone section",
                "slug": "phone-section",
                "description": "",
                "icon": "phone",
                "sort_order": "0",
                "is_active": "on",
            },
        )
        self.assertRedirects(create_response, reverse("site_management:area_manager", args=[ContentSection.Area.HOMEPAGE]))
        self.assertTrue(
            ContentSection.objects.filter(slug="phone-section", icon="phone").exists()
        )

        section = ContentSection.objects.create(
            area=ContentSection.Area.HOMEPAGE,
            title="Image upload test",
            slug="image-upload-test",
        )
        item_response = self.client.get(
            reverse("site_management:item_create", args=[section.pk])
        )
        self.assertEqual(item_response.status_code, 200)
        self.assertContains(item_response, "management-icon-picker")
        self.assertContains(item_response, 'name="image"')
        self.assertContains(item_response, 'name="secondary_image"')
        self.assertContains(item_response, 'name="thumbnail_image"')

    def test_staff_can_customize_homepage_menu_and_footer_through_crud(self):
        self.client.force_login(self.staff)
        home_section = ContentSection.objects.create(
            area=ContentSection.Area.HOMEPAGE,
            title="Custom announcements",
            slug="custom-announcements",
            description="A custom homepage area.",
            sort_order=100,
        )
        response = self.client.post(
            reverse("site_management:item_create", args=[home_section.pk]),
            {
                "parent": "",
                "label": "Read the new guide",
                "body": "A customized call to action.",
                "url": "/guides/new/",
                "style": ContentItem.Style.BUTTON,
                "icon": "",
                "sort_order": "10",
                "open_new_tab": "",
                "is_active": "on",
                "show_on_homepage": "on",
            },
        )
        self.assertRedirects(response, reverse("site_management:area_manager", args=[home_section.area]))

        nav_section = ContentSection.objects.get(slug="main-navigation")
        parent = ContentItem.objects.create(
            section=nav_section,
            label="Resources",
            sort_order=100,
        )
        response = self.client.post(
            reverse("site_management:item_create", args=[nav_section.pk]),
            {
                "parent": parent.pk,
                "label": "Study resources",
                "body": "",
                "url": "https://example.org/resources",
                "style": ContentItem.Style.LINK,
                "icon": "",
                "sort_order": "110",
                "open_new_tab": "on",
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("site_management:area_manager", args=[nav_section.area]))

        response = self.client.post(
            reverse("site_management:settings"),
            {
                "site_name": "Niyukti Portal",
                "tagline": "Verified career updates",
                "logo_text": "NP",
                "logo_url": "",
                "favicon_url": "",
                "header_text": "CAREER DESK",
                "hero_title": "Find your next opportunity",
                "hero_description": "Fresh and useful recruitment updates.",
                "announcement": "New guide available",
                "hero_note_title": "Verified updates",
                "hero_note_body": "Read official notices before applying.",
                "hero_note_footer": "Check source websites for final details.",
                "footer_description": "Helpful information for applicants.",
                "footer_contact": "Email support@example.org",
                "footer_copyright": "Niyukti Portal",
                "footer_disclaimer": "Always verify notices with the authority.",
            },
        )
        self.assertRedirects(response, reverse("site_management:settings"))

        public = self.client.get(reverse("home"))
        self.assertContains(public, "Niyukti Portal")
        self.assertContains(public, "Find your next opportunity")
        self.assertContains(public, "Read the new guide")
        self.assertContains(public, "/guides/new/")
        self.assertContains(public, "Study resources")
        self.assertContains(public, "https://example.org/resources")
        self.assertContains(public, "Helpful information for applicants.")
        self.assertNotContains(public, "/site-management/")

    def test_staff_delete_requires_confirmation_and_post(self):
        self.client.force_login(self.staff)
        section = ContentSection.objects.create(
            area=ContentSection.Area.HOMEPAGE,
            title="Disposable test section",
            slug="disposable-test-section",
        )
        item = ContentItem.objects.create(section=section, label="Temporary item")

        confirmation = self.client.get(
            reverse("site_management:section_delete", args=[section.pk])
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertTrue(ContentSection.objects.filter(pk=section.pk).exists())

        response = self.client.post(
            reverse("site_management:section_delete", args=[section.pk])
        )

        self.assertRedirects(response, reverse("site_management:area_manager", args=[section.area]))
        self.assertFalse(ContentSection.objects.filter(pk=section.pk).exists())
        self.assertFalse(ContentItem.objects.filter(pk=item.pk).exists())

    def test_unsafe_link_schemes_are_rejected(self):
        self.client.force_login(self.staff)
        section = ContentSection.objects.get(slug="main-navigation")
        response = self.client.post(
            reverse("site_management:item_create", args=[section.pk]),
            {
                "parent": "",
                "label": "Unsafe link",
                "body": "",
                "url": "javascript:alert(1)",
                "style": ContentItem.Style.LINK,
                "icon": "",
                "sort_order": "99",
                "open_new_tab": "",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Use a local path or an HTTP/HTTPS URL.")
        self.assertFalse(ContentItem.objects.filter(label="Unsafe link").exists())

    def test_malformed_external_urls_are_rejected_without_server_error(self):
        self.client.force_login(self.staff)
        section = ContentSection.objects.get(slug="main-navigation")

        response = self.client.post(
            reverse("site_management:item_create", args=[section.pk]),
            {
                "parent": "",
                "label": "Malformed link",
                "body": "",
                "url": "https://[",
                "style": ContentItem.Style.LINK,
                "icon": "",
                "sort_order": "99",
                "open_new_tab": "",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Use a valid HTTP/HTTPS URL.")
        self.assertFalse(ContentItem.objects.filter(label="Malformed link").exists())

    def test_cms_item_accepts_png_and_renders_it_on_public_card_and_detail(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.client.force_login(self.staff)
                section = ContentSection.objects.get(slug="results")
                response = self.client.post(
                    reverse("site_management:item_create", args=[section.pk]),
                    {
                        "parent": "",
                        "label": "Image-backed result",
                        "body": "Result information with a preview.",
                        "image": make_png_upload("result-preview.png"),
                        "url": "",
                        "style": ContentItem.Style.LINK,
                        "icon": "",
                        "sort_order": "5",
                        "open_new_tab": "",
                        "is_active": "on",
                        "show_on_homepage": "on",
                    },
                )

                self.assertRedirects(response, reverse("site_management:area_manager", args=[section.area]))
                item = ContentItem.objects.get(label="Image-backed result")
                self.assertTrue(item.image.name.startswith("cms/content_items/"))
                image_url = item.image.url
                self.assertTrue(item.image.storage.exists(item.image.name))
                with item.image.open("rb") as stored_image:
                    self.assertEqual(stored_image.read(8), b"\x89PNG\r\n\x1a\n")

                listing = self.client.get(
                    reverse("accounts:section_list", args=[section.slug])
                )
                self.assertContains(listing, image_url)
                self.assertContains(listing, 'class="portal-content-image"')

                detail = self.client.get(
                    reverse(
                        "accounts:section_item_detail",
                        args=[section.slug, item.pk],
                    )
                )
                self.assertContains(detail, image_url)
                self.assertContains(detail, 'class="portal-content-image"')

                homepage = self.client.get(reverse("home"))
                self.assertContains(homepage, image_url)

    def test_blocks_without_an_image_render_without_an_empty_preview(self):
        section = ContentSection.objects.get(slug="results")
        item = section.items.filter(is_active=True, parent__isnull=True).first()

        listing = self.client.get(reverse("accounts:section_list", args=[section.slug]))
        detail = self.client.get(
            reverse(
                "accounts:section_item_detail",
                args=[section.slug, item.pk],
            )
        )

        self.assertNotContains(listing, "portal-content-image-box")
        self.assertNotContains(detail, "portal-content-image-box")

    def test_cms_item_accepts_supported_image_formats_for_every_media_field(self):
        formats = (
            ("png", "PNG"),
            ("jpg", "JPEG"),
            ("jpeg", "JPEG"),
            ("webp", "WEBP"),
        )
        self.client.force_login(self.staff)
        section = ContentSection.objects.get(slug="results")

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                for field_name in ("image", "secondary_image", "thumbnail_image"):
                    for extension, image_format in formats:
                        label = f"{field_name}-{extension}"
                        response = self.client.post(
                            reverse("site_management:item_create", args=[section.pk]),
                            {
                                "parent": "",
                                "label": label,
                                "body": "Image format validation.",
                                field_name: make_image_upload(
                                    f"test.{extension}", image_format
                                ),
                                "url": "",
                                "style": ContentItem.Style.LINK,
                                "icon": "",
                                "sort_order": "5",
                                "open_new_tab": "",
                                "is_active": "on",
                            },
                        )
                        self.assertRedirects(
                            response, reverse("site_management:area_manager", args=[section.area])
                        )
                        item = ContentItem.objects.get(label=label)
                        with getattr(item, field_name).open("rb") as stored_image:
                            with Image.open(stored_image) as decoded_image:
                                self.assertEqual(decoded_image.format, image_format)

    def test_website_page_images_support_formats_preview_replace_and_clear(self):
        formats = (
            ("png", "PNG"),
            ("jpg", "JPEG"),
            ("jpeg", "JPEG"),
            ("webp", "WEBP"),
        )
        self.client.force_login(self.staff)

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                page = WebsitePage.objects.get(
                    page_type=WebsitePage.PageType.CONTACT_US
                )
                edit_url = reverse(
                    "site_management:website_page_edit", args=[page.pk]
                )
                previous_name = ""
                for extension, image_format in formats:
                    with self.captureOnCommitCallbacks(execute=True):
                        response = self.client.post(
                            edit_url,
                            {
                                "title": page.title,
                                "description": page.description,
                                "image": make_image_upload(
                                    f"page.{extension}", image_format
                                ),
                                "is_published": "on",
                            },
                        )
                    self.assertRedirects(
                        response, reverse("site_management:website_pages")
                    )
                    page.refresh_from_db()
                    current_name = page.image.name
                    self.assertTrue(page.image.storage.exists(current_name))
                    if previous_name:
                        self.assertFalse(page.image.storage.exists(previous_name))
                    previous_name = current_name

                change_page = self.client.get(edit_url)
                self.assertContains(change_page, 'name="image-clear"')
                self.assertContains(change_page, 'id="website-page-image-preview"')
                self.assertContains(change_page, page.image.url)
                self.assertContains(
                    change_page, ".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
                )

                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(
                        edit_url,
                        {
                            "title": page.title,
                            "description": page.description,
                            "image-clear": "on",
                            "is_published": "on",
                        },
                    )
                self.assertRedirects(
                    response, reverse("site_management:website_pages")
                )
                page.refresh_from_db()
                self.assertFalse(page.image)
                self.assertFalse(page.image.storage.exists(previous_name))

    def test_cms_item_rejects_unsupported_and_corrupt_uploads(self):
        self.client.force_login(self.staff)
        section = ContentSection.objects.get(slug="results")
        unsupported = make_image_upload("unsupported.bmp", "BMP")

        response = self.client.post(
            reverse("site_management:item_create", args=[section.pk]),
            {
                "parent": "",
                "label": "Rejected BMP",
                "body": "Unsupported image.",
                "image": unsupported,
                "url": "",
                "style": ContentItem.Style.LINK,
                "icon": "",
                "sort_order": "5",
                "open_new_tab": "",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Supported image formats are PNG, JPG, JPEG, and WebP."
        )
        self.assertFalse(ContentItem.objects.filter(label="Rejected BMP").exists())

        corrupt_image = SimpleUploadedFile(
            "corrupt.png", b"not an image", content_type="image/png"
        )
        response = self.client.post(
            reverse("site_management:item_create", args=[section.pk]),
            {
                "parent": "",
                "label": "Rejected corrupt image",
                "body": "Corrupt image.",
                "image": corrupt_image,
                "url": "",
                "style": ContentItem.Style.LINK,
                "icon": "",
                "sort_order": "6",
                "open_new_tab": "",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "valid, uncorrupted PNG, JPG, JPEG, or WebP image"
        )
        self.assertFalse(
            ContentItem.objects.filter(label="Rejected corrupt image").exists()
        )

    def test_cms_item_rejects_oversized_image(self):
        self.client.force_login(self.staff)
        section = ContentSection.objects.get(slug="results")
        oversized_upload = SimpleUploadedFile(
            "oversized.png", self._large_png_bytes(), content_type="image/png"
        )

        with override_settings(CMS_MAX_IMAGE_SIZE=1024 * 1024):
            response = self.client.post(
                reverse("site_management:item_create", args=[section.pk]),
                {
                    "parent": "",
                    "label": "Rejected oversized image",
                    "body": "Oversized image.",
                    "image": oversized_upload,
                    "url": "",
                    "style": ContentItem.Style.LINK,
                    "icon": "",
                    "sort_order": "7",
                    "open_new_tab": "",
                    "is_active": "on",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no larger than 1 MB")
        self.assertFalse(
            ContentItem.objects.filter(label="Rejected oversized image").exists()
        )

    @staticmethod
    def _large_png_bytes():
        image = Image.frombytes("RGB", (1500, 1500), os.urandom(1500 * 1500 * 3))
        image_bytes = BytesIO()
        image.save(image_bytes, format="PNG")
        return image_bytes.getvalue()

    def test_cms_item_image_can_be_replaced_or_cleared(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.client.force_login(self.staff)
                section = ContentSection.objects.get(slug="results")
                item = ContentItem.objects.create(
                    section=section,
                    label="Replaceable image",
                )
                edit_url = reverse("site_management:item_edit", args=[item.pk])
                data = {
                    "parent": "",
                    "label": item.label,
                    "body": "Description for this image block.",
                    "image": make_png_upload("first.png"),
                    "url": "",
                    "style": ContentItem.Style.LINK,
                    "icon": "",
                    "sort_order": "5",
                    "open_new_tab": "",
                    "is_active": "on",
                    "show_on_homepage": "on",
                }
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(edit_url, data)
                self.assertRedirects(response, reverse("site_management:area_manager", args=[section.area]))
                item.refresh_from_db()
                first_image = item.image.name
                self.assertTrue(first_image)

                data["image"] = make_png_upload("replacement.png", color="green")
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(edit_url, data)
                self.assertRedirects(response, reverse("site_management:area_manager", args=[section.area]))
                item.refresh_from_db()
                self.assertTrue(item.image.name)
                self.assertNotEqual(item.image.name, first_image)
                self.assertFalse(item.image.storage.exists(first_image))

                data.pop("image")
                data["image-clear"] = "on"
                replacement_image = item.image.name
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(edit_url, data)
                self.assertRedirects(response, reverse("site_management:area_manager", args=[section.area]))
                item.refresh_from_db()
                self.assertFalse(item.image)
                self.assertFalse(item.image.storage.exists(replacement_image))

    def test_homepage_block_saves_with_only_required_description(self):
        self.client.force_login(self.staff)
        section = ContentSection.objects.get(slug="results")
        response = self.client.post(
            reverse("site_management:item_create", args=[section.pk]),
            {
                "parent": "",
                "label": "",
                "body": "The only required content field is a clear description.",
                "sort_order": "20",
            },
        )

        self.assertRedirects(response, reverse("site_management:area_manager", args=[section.area]))
        item = ContentItem.objects.get(
            section=section,
            body="The only required content field is a clear description.",
        )
        self.assertEqual(item.label, "")
        self.assertFalse(item.image)
        self.assertFalse(item.url)

    def test_homepage_block_saves_combinations_of_optional_builder_fields(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.client.force_login(self.staff)
                section = ContentSection.objects.get(slug="results")
                response = self.client.post(
                    reverse("site_management:item_create", args=[section.pk]),
                    {
                        "parent": "",
                        "label": "Optional title",
                        "body": "Main description remains present.",
                        "subtitle": "A useful subtitle",
                        "short_description": "Short summary",
                        "additional_description": "More details",
                        "badge_text": "NEW",
                        "eyebrow_text": "EXAM UPDATE",
                        "highlight_text": "Important highlight",
                        "caption": "A caption",
                        "source_name": "Official source",
                        "published_at": "2026-10-13",
                        "primary_link_text": "Apply now",
                        "url": "https://example.org/apply",
                        "secondary_link_text": "Read details",
                        "secondary_link_url": "https://example.org/details",
                        "call_to_action": "Review the notice",
                        "link_title": "Application details",
                        "accessible_label": "Open application information",
                        "image": make_png_upload("primary.png"),
                        "secondary_image": make_png_upload("secondary.png", "green"),
                        "thumbnail_image": make_png_upload("thumbnail.png", "blue"),
                        "image_alt": "Application notice artwork",
                        "image_caption": "Official artwork",
                        "image_position": ContentItem.ImagePosition.RIGHT,
                        "image_size": ContentItem.ImageSize.MEDIUM,
                        "image_fit": ContentItem.ImageFit.CONTAIN,
                        "style": ContentItem.Style.BUTTON,
                        "icon": "notice",
                        "block_type": ContentItem.BlockType.NOTICE,
                        "background_color": "#112233",
                        "text_color": "#FFFFFF",
                        "border_color": "#445566",
                        "border_radius": ContentItem.BorderRadius.MEDIUM,
                        "spacing": ContentItem.Spacing.RELAXED,
                        "content_alignment": ContentItem.Alignment.CENTER,
                        "layout": ContentItem.Layout.FEATURE,
                        "badge_color": ContentItem.BadgeColor.CYAN,
                        "custom_css_class": "campaign-card featured",
                        "show_on_desktop": "on",
                        "show_on_tablet": "on",
                        "show_on_mobile": "on",
                        "sort_order": "21",
                        "is_active": "on",
                        "is_featured": "on",
                        "show_on_homepage": "on",
                        "publish_at": "2026-10-13 10:00:00",
                        "expires_at": "2026-10-20 10:00:00",
                        "internal_notes": "Internal CMS note.",
                    },
                )

                self.assertRedirects(response, reverse("site_management:area_manager", args=[section.area]))
                item = ContentItem.objects.get(label="Optional title")
                self.assertEqual(item.secondary_link_text, "Read details")
                self.assertEqual(item.image_position, ContentItem.ImagePosition.RIGHT)
                self.assertEqual(item.background_color, "#112233")
                self.assertTrue(item.is_featured)
                self.assertTrue(item.secondary_image)
                self.assertTrue(item.thumbnail_image)

                homepage = self.client.get(reverse("home"))
                self.assertContains(homepage, "Optional title")
                self.assertContains(homepage, "Application notice artwork")
                self.assertContains(homepage, "campaign-card featured")
                self.assertContains(homepage, "https://example.org/apply")
                self.assertContains(homepage, "https://example.org/details")

                detail = self.client.get(
                    reverse(
                        "accounts:section_item_detail",
                        args=[section.slug, item.pk],
                    )
                )
                self.assertContains(detail, "More details")
                self.assertContains(detail, "Review the notice")
                self.assertContains(detail, "https://example.org/details")

    def test_homepage_description_is_required_and_optional_headings_do_not_render_empty(self):
        self.client.force_login(self.staff)
        section = ContentSection.objects.get(slug="results")
        response = self.client.post(
            reverse("site_management:item_create", args=[section.pk]),
            {
                "parent": "",
                "label": "",
                "body": "",
                "sort_order": "20",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertFalse(
            ContentItem.objects.filter(section=section, body="").exists()
        )

    def test_public_homepage_contains_no_admin_entry_point(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("site_management:dashboard"))
        self.assertNotContains(response, "Site Management")
        self.assertEqual(WebsiteSettings.objects.count(), 1)

    def test_saving_block_with_only_description_succeeds_and_renders_cleanly(self):
        self.client.force_login(self.staff)
        section = ContentSection.objects.get(slug="results")
        response = self.client.post(
            reverse("site_management:item_create", args=[section.pk]),
            {
                "parent": "",
                "label": "",
                "body": "Pure description without any title or optional attributes.",
                "sort_order": "50",
                "is_active": "on",
                "show_on_homepage": "on",
            },
        )
        self.assertRedirects(response, reverse("site_management:area_manager", args=[section.area]))

        item = ContentItem.objects.get(
            section=section,
            body="Pure description without any title or optional attributes.",
        )
        self.assertEqual(item.label, "")
        self.assertFalse(item.image)
        self.assertFalse(item.url)
        self.assertFalse(item.button_text)
        self.assertFalse(item.button_url)
        self.assertTrue(item.is_active)
        self.assertTrue(item.show_on_homepage)
        self.assertIn("Pure description", str(item))

        # Check homepage rendering
        homepage = self.client.get(reverse("home"))
        self.assertEqual(homepage.status_code, 200)
        self.assertContains(homepage, "Pure description without any title or optional attributes.")
        self.assertNotContains(homepage, "<h3></h3>")
        self.assertNotContains(homepage, 'class="portal-card-subtitle"')
        self.assertNotContains(homepage, 'class="portal-card-highlight"')
        self.assertNotContains(homepage, 'class="portal-card-cta"')

        # Check section listing page
        listing = self.client.get(reverse("accounts:section_list", args=[section.slug]))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "Pure description without any title or optional attributes.")
        self.assertNotContains(listing, "<h2></h2>")
        self.assertNotContains(listing, 'class="portal-content-image-box"')

        # Check item detail page
        detail = self.client.get(reverse("accounts:section_item_detail", args=[section.slug, item.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Pure description without any title or optional attributes.")
        self.assertNotContains(detail, '<h1 id="item-title">')
        self.assertNotContains(detail, 'class="portal-detail-image-frame"')
        self.assertNotContains(detail, 'class="portal-detail-actions"')

    def test_saving_block_with_dedicated_button_and_image_alignment(self):
        self.client.force_login(self.staff)
        section = ContentSection.objects.get(slug="results")
        response = self.client.post(
            reverse("site_management:item_create", args=[section.pk]),
            {
                "parent": "",
                "label": "Block with dedicated button",
                "body": "Main description content.",
                "button_text": "Check Result Now",
                "button_url": "https://example.org/result-check",
                "image_alignment": "center",
                "call_to_action": "Download your scorecard today.",
                "sort_order": "51",
                "is_active": "on",
                "show_on_homepage": "on",
            },
        )
        self.assertRedirects(response, reverse("site_management:area_manager", args=[section.area]))

        item = ContentItem.objects.get(label="Block with dedicated button")
        self.assertEqual(item.button_text, "Check Result Now")
        self.assertEqual(item.button_url, "https://example.org/result-check")
        self.assertEqual(item.image_alignment, "center")
        self.assertEqual(item.call_to_action, "Download your scorecard today.")

        # Homepage rendering has dedicated button and CTA
        homepage = self.client.get(reverse("home"))
        self.assertContains(homepage, "Check Result Now")
        self.assertContains(homepage, "https://example.org/result-check")
        self.assertContains(homepage, "Download your scorecard today.")

        # Detail page rendering has CTA and dedicated CTA button
        detail = self.client.get(reverse("accounts:section_item_detail", args=[section.slug, item.pk]))
        self.assertContains(detail, "Check Result Now")
        self.assertContains(detail, "https://example.org/result-check")
        self.assertContains(detail, "Download your scorecard today.")
        self.assertContains(detail, "portal-cms-button-cta")

    def test_empty_url_or_text_never_renders_broken_buttons(self):
        section = ContentSection.objects.get(slug="results")

        # 1. Block with URL but no link text and no label
        item1 = ContentItem.objects.create(
            section=section,
            label="",
            body="Block with URL but no primary text.",
            url="https://example.org/orphan-url",
            primary_link_text="",
        )
        # 2. Block with button_url but no button_text
        item2 = ContentItem.objects.create(
            section=section,
            label="Incomplete button",
            body="Block with button url but empty button text.",
            button_url="https://example.org/btn-url",
            button_text="",
        )
        # 3. Block with button_text but empty button_url
        item3 = ContentItem.objects.create(
            section=section,
            label="Incomplete button url",
            body="Block with button text but empty button url.",
            button_url="",
            button_text="Click here",
        )
        # 4. Block with secondary_link_url but empty secondary_link_text
        item4 = ContentItem.objects.create(
            section=section,
            label="Incomplete secondary link",
            body="Block with secondary url but empty text.",
            secondary_link_url="https://example.org/sec",
            secondary_link_text="",
        )

        homepage = self.client.get(reverse("home"))
        self.assertNotContains(homepage, "https://example.org/orphan-url")
        self.assertNotContains(homepage, "https://example.org/btn-url")
        self.assertNotContains(homepage, "https://example.org/sec")

        # For item1, detail page should not render actions block
        detail1 = self.client.get(reverse("accounts:section_item_detail", args=[section.slug, item1.pk]))
        self.assertNotContains(detail1, 'class="portal-detail-actions"')

        # For item2, button should not render
        detail2 = self.client.get(reverse("accounts:section_item_detail", args=[section.slug, item2.pk]))
        self.assertNotContains(detail2, "https://example.org/btn-url")

        # For item3, button should not render
        detail3 = self.client.get(reverse("accounts:section_item_detail", args=[section.slug, item3.pk]))
        self.assertNotContains(detail3, "Click here")

    def test_django_admin_content_item_changelist_and_form(self):
        self.client.force_login(self.staff)
        section = ContentSection.objects.get(slug="results")
        item = ContentItem.objects.create(
            section=section,
            label="",
            body="Admin test block with only description.",
        )

        # Changelist loads
        changelist = self.client.get("/admin/site_management/contentitem/")
        self.assertEqual(changelist.status_code, 200)
        self.assertContains(changelist, "Admin test block with only description")

        # Changeform loads with fieldsets
        changeform = self.client.get(f"/admin/site_management/contentitem/{item.pk}/change/")
        self.assertEqual(changeform.status_code, 200)
        self.assertContains(changeform, "Basic Content")
        self.assertContains(changeform, "Links and Buttons")
        self.assertContains(changeform, "Images and Media")
        self.assertContains(changeform, "Appearance and Layout")
        self.assertContains(changeform, "Publishing")
        self.assertContains(changeform, "No image uploaded")

    def test_existing_content_remains_intact(self):
        # All default sections exist
        sections = ContentSection.objects.values_list("slug", flat=True)
        self.assertIn("jobs", sections)
        self.assertIn("results", sections)
        self.assertIn("admit-cards", sections)
        self.assertIn("answer-keys", sections)

        # Homepage responds successfully and contains existing sections
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Latest Results")
        self.assertContains(response, "Admit Cards")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AdminRedesignTests(TestCase):
    """Covers the redesigned dashboard, grouped sidebar, and per-area editors."""

    def setUp(self):
        from jobs.models import Job

        self.admin = User.objects.create_superuser(
            username="redesignadmin",
            email="redesignadmin@example.com",
            password="Strongpass123",
        )
        self.member = User.objects.create_user(
            username="redesignmember",
            email="redesignmember@example.com",
            password="Strongpass123",
        )
        self.staff = User.objects.create_user(
            username="redesignstaff",
            email="redesignstaff@example.com",
            password="Strongpass123",
        )
        self.staff.is_staff = True
        self.staff.save()
        Job.objects.create(
            title="Published Test Result",
            organization="Test Commission",
            qualification="Graduate",
            status="published",
            is_verified=True,
        )
        Job.objects.create(
            title="Draft Test Result",
            organization="Test Commission",
            qualification="Graduate",
            status="draft",
        )

    def test_area_manager_renders_for_every_area(self):
        self.client.force_login(self.admin)
        for area, label in ContentSection.Area.choices:
            with self.subTest(area=area):
                response = self.client.get(
                    reverse("site_management:area_manager", args=[area])
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, label)
                self.assertContains(response, "New section")

    def test_area_manager_rejects_unknown_area(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("site_management:area_manager", args=["does-not-exist"])
        )
        self.assertEqual(response.status_code, 404)

    def test_area_manager_requires_staff(self):
        response = self.client.get(
            reverse("site_management:area_manager", args=["homepage"])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("site_management:login"), response["Location"])

        self.client.force_login(self.member)
        denied = self.client.get(
            reverse("site_management:area_manager", args=["homepage"])
        )
        self.assertEqual(denied.status_code, 302)

    def test_dashboard_reports_real_statistics(self):
        Exam.objects.create(title="Live exam", status=Exam.Status.PUBLISHED)
        Exam.objects.create(title="Draft exam", status=Exam.Status.DRAFT)
        PreviousPaper.objects.create(
            title="Live paper", status=PreviousPaper.Status.PUBLISHED
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("site_management:dashboard"))
        stats = response.context["stats"]
        self.assertEqual(stats["exams_published"], 1)
        self.assertEqual(stats["resources_published"], 1)
        self.assertContains(response, "Published exams")
        self.assertNotContains(response, "Recent activity")
        self.assertNotContains(response, "Recommended setup")

    def test_dashboard_shows_unread_contact_messages(self):
        self.client.force_login(self.admin)
        ContactSubmission.objects.create(
            name="Applicant",
            phone_number="9876543210",
            email="applicant@example.com",
            subject="Question",
            message="Where is the admit card for the test exam?",
        )
        response = self.client.get(reverse("site_management:dashboard"))
        self.assertEqual(response.context["stats"]["contact_unread"], 1)

    def test_grouped_sidebar_links_to_working_screens(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("site_management:dashboard"))
        content = response.content.decode()
        for url in (
            reverse("site_management:exams"),
            reverse("site_management:resource_list", args=["answer-sheets"]),
            reverse("site_management:resource_list", args=["registration-forms"]),
            reverse("site_management:resource_list", args=["previous-papers"]),
            reverse("site_management:resource_list", args=["results"]),
            reverse("site_management:area_manager", args=["navigation"]),
            reverse("site_management:area_manager", args=["footer"]),
            reverse("site_management:website_pages"),
            reverse("site_management:settings"),
        ):
            with self.subTest(url=url):
                self.assertIn(url, content)
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_non_superuser_sidebar_hides_admin_only_links(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("site_management:dashboard"))
        content = response.content.decode()
        self.assertNotIn(reverse("admin:jobs_job_changelist"), content)
        self.assertNotIn("SYSTEM MANAGEMENT", content)

    def test_sidebar_exposes_the_fixed_sections_in_order(self):
        from .navigation import build_navigation

        keys = [section["key"] for section in build_navigation(self.admin)]
        self.assertEqual(
            keys,
            [
                "exams",
                "upcoming-exams",
                "recent-exams",
                "answer-sheets",
                "registration-forms",
                "previous-papers",
                "results",
                "header",
                "footer",
                "comments",
                "users",
                "ai",
            ],
        )

    def test_single_screen_sections_redirect_to_their_editor(self):
        self.client.force_login(self.admin)
        expected = {
            "upcoming-exams": reverse("site_management:upcoming_exams"),
            "recent-exams": reverse("site_management:recent_exams"),
            "users": reverse("site_management:user_list"),
            "ai": reverse("site_management:ai_status"),
            "comments": reverse("site_management:comment_moderation"),
        }
        for key, target in expected.items():
            with self.subTest(section=key):
                response = self.client.get(
                    reverse("site_management:section_overview", args=[key])
                )
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], target)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ContentPDFTests(TestCase):
    """PDF uploads and optional links on Results/Admit Card/Papers content."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="pdfadmin",
            email="pdfadmin@example.com",
            password="Strongpass123",
        )
        self.staff = User.objects.create_user(
            username="pdfstaff",
            email="pdfstaff@example.com",
            password="Strongpass123",
        )
        self.staff.is_staff = True
        self.staff.save()
        self.section = ContentSection.objects.get(slug="results")
        self.create_url = reverse(
            "site_management:item_create", args=[self.section.pk]
        )

    def _post_pdf(self, pdf_upload, label, **extra):
        data = {
            "parent": "",
            "label": label,
            "body": "Official document details.",
            "pdf_file": pdf_upload,
            "url": "",
            "style": ContentItem.Style.LINK,
            "icon": "",
            "sort_order": extra.pop("sort_order", "5"),
            "open_new_tab": "",
            "is_active": "on",
            "show_on_homepage": "on",
        }
        data.update(extra)
        return self.client.post(self.create_url, data)

    def test_pdf_field_is_offered_for_pdf_sections_only(self):
        self.client.force_login(self.superuser)
        homepage_section_form = self.client.get(self.create_url)
        self.assertContains(homepage_section_form, 'name="pdf_file"')
        self.assertContains(homepage_section_form, 'accept=".pdf,application/pdf"')

        navigation_section = ContentSection.objects.get(slug="main-navigation")
        navigation_form = self.client.get(
            reverse("site_management:item_create", args=[navigation_section.pk])
        )
        self.assertNotContains(navigation_form, 'name="pdf_file"')

    def test_pdf_upload_is_stored_and_rendered_as_a_download_link(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.client.force_login(self.superuser)
                response = self._post_pdf(make_pdf_upload("ssc-result.pdf"), "SSC Result 2026")

                self.assertRedirects(
                    response,
                    reverse("site_management:area_manager", args=["homepage"]),
                )
                item = ContentItem.objects.get(label="SSC Result 2026")
                self.assertTrue(item.pdf_file.name.startswith("cms/content_pdfs/"))
                self.assertTrue(item.pdf_file.storage.exists(item.pdf_file.name))
                with item.pdf_file.open("rb") as stored_pdf:
                    self.assertEqual(stored_pdf.read(5), b"%PDF-")

                listing = self.client.get(
                    reverse("accounts:section_list", args=[self.section.slug])
                )
                self.assertContains(listing, "Click here to download the PDF")
                self.assertContains(listing, 'class="portal-hand-link"')
                self.assertContains(listing, item.pdf_file.url)
                self.assertContains(listing, 'rel="noopener noreferrer"')

                detail = self.client.get(
                    reverse(
                        "accounts:section_item_detail",
                        args=[self.section.slug, item.pk],
                    )
                )
                self.assertContains(detail, "Click here to download the PDF")
                self.assertContains(detail, item.pdf_file.url)

                homepage = self.client.get(reverse("home"))
                self.assertContains(homepage, "Click here to download the PDF")

    def test_replacement_and_deletion_clean_up_the_stored_pdf(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.client.force_login(self.superuser)
                self._post_pdf(make_pdf_upload("first.pdf"), "Replaceable PDF")
                item = ContentItem.objects.get(label="Replaceable PDF")
                storage = item.pdf_file.storage
                first_name = item.pdf_file.name

                with self.captureOnCommitCallbacks(execute=True):
                    self.client.post(
                        reverse("site_management:item_edit", args=[item.pk]),
                        {
                            "parent": "",
                            "label": "Replaceable PDF",
                            "body": "Official document details.",
                            "pdf_file": make_pdf_upload("second.pdf"),
                            "url": "",
                            "style": ContentItem.Style.LINK,
                            "icon": "",
                            "sort_order": "5",
                            "open_new_tab": "",
                            "is_active": "on",
                        },
                    )
                item.refresh_from_db()
                self.assertTrue(item.pdf_file.name.endswith("second.pdf"))
                self.assertFalse(storage.exists(first_name))

                with self.captureOnCommitCallbacks(execute=True):
                    self.client.post(
                        reverse("site_management:item_delete", args=[item.pk])
                    )
                self.assertFalse(ContentItem.objects.filter(pk=item.pk).exists())
                self.assertFalse(storage.exists(item.pdf_file.name))

    def test_non_pdf_and_corrupt_uploads_are_rejected(self):
        self.client.force_login(self.superuser)

        renamed = make_pdf_upload("notes.txt", b"%PDF-1.4 disguised")
        response = self._post_pdf(renamed, "Rejected text file")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "the filename must end in .pdf")
        self.assertFalse(ContentItem.objects.filter(label="Rejected text file").exists())

        corrupt = make_pdf_upload("corrupt.pdf", b"this is not a pdf")
        response = self._post_pdf(corrupt, "Rejected corrupt PDF")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid, uncorrupted PDF file")
        self.assertFalse(
            ContentItem.objects.filter(label="Rejected corrupt PDF").exists()
        )

    def test_oversized_pdf_is_rejected(self):
        self.client.force_login(self.superuser)
        oversized = make_pdf_upload("huge.pdf", b"%PDF-1.4" + b"0" * (2 * 1024 * 1024))

        with override_settings(CMS_MAX_PDF_SIZE=1024 * 1024):
            response = self._post_pdf(oversized, "Rejected oversized PDF")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no larger than 1 MB")
        self.assertFalse(
            ContentItem.objects.filter(label="Rejected oversized PDF").exists()
        )

    def test_pdf_uploads_require_staff_and_a_post_request(self):
        anonymous = self.client.get(self.create_url)
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn(reverse("site_management:login"), anonymous["Location"])

        self.client.force_login(self.staff)
        get_response = self.client.get(self.create_url)
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, 'name="pdf_file"')

        self.client.force_login(self.superuser)
        no_csrf = Client(enforce_csrf_checks=True)
        no_csrf.force_login(self.superuser)
        blocked = no_csrf.post(
            self.create_url,
            {"label": "No CSRF PDF", "body": "x", "style": ContentItem.Style.LINK},
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertFalse(ContentItem.objects.filter(label="No CSRF PDF").exists())

    def test_item_without_pdf_or_links_renders_no_placeholder(self):
        item = ContentItem.objects.create(
            section=self.section,
            label="Plain notice without attachments",
            body="No downloadable documents here.",
            sort_order=1,
        )

        detail = self.client.get(
            reverse(
                "accounts:section_item_detail", args=[self.section.slug, item.pk]
            )
        )
        self.assertNotContains(detail, "portal-hand-link")
        self.assertNotContains(detail, "Click here to download the PDF")

        listing = self.client.get(
            reverse("accounts:section_list", args=[self.section.slug])
        )
        self.assertNotContains(listing, "portal-card-extra-links")

    def test_optional_links_render_blue_hand_links_with_edited_text(self):
        item = ContentItem.objects.create(
            section=self.section,
            label="Notice with extra links",
            body="Two editable links.",
            sort_order=2,
        )
        ContentLink.objects.create(
            content_item=item,
            label="Download hall ticket",
            url="https://example.org/hall-ticket.pdf",
            open_new_tab=True,
        )

        listing = self.client.get(
            reverse("accounts:section_list", args=[self.section.slug])
        )
        self.assertContains(listing, 'class="portal-hand-link"')
        self.assertContains(listing, "Download hall ticket")
        self.assertContains(listing, 'href="https://example.org/hall-ticket.pdf"')

        detail = self.client.get(
            reverse(
                "accounts:section_item_detail", args=[self.section.slug, item.pk]
            )
        )
        self.assertContains(detail, "Download hall ticket")

    def test_unpublished_pdf_item_is_hidden_and_shows_no_public_link(self):
        self.client.force_login(self.superuser)
        item = ContentItem.objects.create(
            section=self.section,
            label="Draft result PDF",
            body="Not published yet.",
            is_active=False,
            sort_order=3,
        )

        listing = self.client.get(
            reverse("accounts:section_list", args=[self.section.slug])
        )
        self.assertNotContains(listing, "Draft result PDF")

        response = self.client.post(
            reverse("site_management:item_edit", args=[item.pk]),
            {
                "parent": "",
                "label": "Draft result PDF",
                "body": "Not published yet.",
                "url": "",
                "style": ContentItem.Style.LINK,
                "icon": "",
                "sort_order": "3",
                "open_new_tab": "",
            },
        )
        self.assertRedirects(
            response,
            reverse("site_management:area_manager", args=["homepage"]),
        )
        item.refresh_from_db()
        self.assertFalse(item.is_active)

        published_listing = self.client.get(
            reverse("accounts:section_list", args=[self.section.slug])
        )
        self.assertNotContains(published_listing, "Draft result PDF")

    def test_area_manager_flags_items_with_an_attached_pdf(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.client.force_login(self.superuser)
                self._post_pdf(make_pdf_upload("flagged.pdf"), "Flagged PDF entry")

                response = self.client.get(
                    reverse("site_management:area_manager", args=["homepage"])
                )
                self.assertContains(response, "PDF attached")
                self.assertContains(
                    response, "#section-" + self.section.slug
                )


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class UsersManagementTests(TestCase):
    """The Users section manages accounts inside the workspace, not Django Admin."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="workspace_owner",
            email="owner@example.com",
            password="Strongpass123",
        )
        account_perms = Permission.objects.filter(
            content_type__app_label="accounts",
            codename__in=["view_emailuser", "change_emailuser"],
        )
        self.manager = User.objects.create_user(
            username="workspace_manager",
            email="manager@example.com",
            password="Strongpass123",
        )
        self.manager.is_staff = True
        self.manager.user_permissions.add(*account_perms)
        self.manager.save()

        self.plain_staff = User.objects.create_user(
            username="plain_staff",
            email="plain-staff@example.com",
            password="Strongpass123",
        )
        self.plain_staff.is_staff = True
        self.plain_staff.save()

        self.member = User.objects.create_user(
            username="public_member",
            email="member@example.com",
            password="Strongpass123",
        )

    def test_users_sidebar_opens_the_custom_page_not_django_admin(self):
        self.client.force_login(self.superuser)
        dashboard = self.client.get(reverse("site_management:dashboard"))

        self.assertContains(dashboard, reverse("site_management:user_list"))
        self.assertNotContains(
            dashboard, reverse("admin:accounts_emailuser_changelist")
        )

        page = self.client.get(reverse("site_management:user_list"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "owner@example.com")

    def test_sidebar_hides_users_from_staff_without_permission(self):
        self.client.force_login(self.plain_staff)
        content = self.client.get(reverse("site_management:dashboard")).content.decode()

        self.assertNotIn(reverse("site_management:user_list"), content)

    def test_anonymous_and_non_staff_users_are_redirected(self):
        response = self.client.get(reverse("site_management:user_list"))
        self.assertRedirects(
            response,
            f"{reverse('site_management:login')}?next={reverse('site_management:user_list')}",
        )

        self.client.force_login(self.member)
        member_response = self.client.get(reverse("site_management:user_list"))
        self.assertEqual(member_response.status_code, 302)
        self.assertIn(reverse("site_management:login"), member_response["Location"])

    def test_staff_without_permission_is_denied(self):
        self.client.force_login(self.plain_staff)

        self.assertEqual(
            self.client.get(reverse("site_management:user_list")).status_code, 403
        )
        self.assertEqual(
            self.client.get(
                reverse("site_management:user_detail", args=[self.member.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("site_management:user_action", args=[self.member.pk, "deactivate"])
            ).status_code,
            403,
        )
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)

    def test_search_and_role_filters(self):
        self.client.force_login(self.superuser)

        searched = self.client.get(
            reverse("site_management:user_list"), {"q": "public_member"}
        )
        self.assertContains(searched, "member@example.com")
        self.assertNotContains(searched, "owner@example.com")

        staff_only = self.client.get(
            reverse("site_management:user_list"), {"role": "staff"}
        )
        self.assertContains(staff_only, "manager@example.com")
        self.assertNotContains(staff_only, "member@example.com")

    def test_list_is_paginated_and_keeps_filters(self):
        self.client.force_login(self.superuser)
        for index in range(30):
            User.objects.create_user(
                username=f"bulk_user_{index}",
                email=f"bulk{index}@example.com",
                password="Strongpass123",
            )

        page = self.client.get(
            reverse("site_management:user_list"), {"q": "bulk_user_", "page": 2}
        )

        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["page_obj"].paginator.count, 30)
        self.assertEqual(len(page.context["page_obj"].object_list), 5)

    def test_detail_never_shows_or_edits_passwords(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse("site_management:user_detail", args=[self.member.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "member@example.com")
        self.assertNotContains(response, 'type="password"')
        self.assertNotContains(response, 'name="password"')

    def test_detail_edits_only_safe_fields(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("site_management:user_detail", args=[self.member.pk]),
            {"full_name": "Public Member", "email": "New-Member@Example.com"},
        )

        self.assertRedirects(
            response, reverse("site_management:user_detail", args=[self.member.pk])
        )
        self.member.refresh_from_db()
        self.assertEqual(self.member.full_name, "Public Member")
        self.assertEqual(self.member.email, "new-member@example.com")
        self.assertFalse(self.member.is_staff)
        self.assertFalse(self.member.is_superuser)

    def test_duplicate_email_is_rejected(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("site_management:user_detail", args=[self.member.pk]),
            {"full_name": "Public Member", "email": "Owner@Example.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already uses this email address")
        self.member.refresh_from_db()
        self.assertEqual(self.member.email, "member@example.com")

    def test_actions_require_post_and_apply_for_authorized_manager(self):
        self.client.force_login(self.manager)

        self.assertEqual(
            self.client.get(
                reverse("site_management:user_action", args=[self.member.pk, "deactivate"])
            ).status_code,
            405,
        )

        response = self.client.post(
            reverse("site_management:user_action", args=[self.member.pk, "deactivate"]),
            follow=True,
        )
        self.assertContains(response, "no longer sign in")
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)

        self.client.post(
            reverse("site_management:user_action", args=[self.member.pk, "grant-staff"])
        )
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_staff)

    def test_state_changing_actions_require_csrf(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.superuser)
        response = client.post(
            reverse("site_management:user_action", args=[self.member.pk, "deactivate"])
        )

        self.assertEqual(response.status_code, 403)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)

    def test_users_cannot_change_their_own_access(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("site_management:user_action", args=[self.superuser.pk, "deactivate"])
        )

        self.assertEqual(response.status_code, 403)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

    def test_non_superuser_cannot_manage_a_superuser(self):
        self.client.force_login(self.manager)

        action = self.client.post(
            reverse("site_management:user_action", args=[self.superuser.pk, "revoke-staff"])
        )
        self.assertEqual(action.status_code, 403)

        edit = self.client.post(
            reverse("site_management:user_detail", args=[self.superuser.pk]),
            {"full_name": "Renamed", "email": "renamed@example.com"},
        )
        self.assertEqual(edit.status_code, 403)

        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_staff)
        self.assertEqual(self.superuser.full_name, "workspace_owner")
        self.assertEqual(self.superuser.email, "owner@example.com")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ExamsManagementTests(TestCase):
    """Exams are managed from the workspace, never through Django Admin."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="examadmin",
            email="examadmin@example.com",
            password="Strongpass123",
        )
        self.staff = User.objects.create_user(
            username="examstaff",
            email="examstaff@example.com",
            password="Strongpass123",
        )
        self.staff.is_staff = True
        self.staff.save()
        self.member = User.objects.create_user(
            username="exammember",
            email="exammember@example.com",
            password="Strongpass123",
        )

    def _post_exam(self, title="SSC CGL 2026", **extra):
        data = {
            "title": title,
            "description": "Official exam announcement.",
            "status": Exam.Status.PUBLISHED,
            "publish_at": "",
            "expires_at": "",
            "sort_order": "0",
            "is_active": "on",
        }
        data.update(extra)
        return self.client.post(reverse("site_management:exam_create"), data)

    def test_exams_manager_renders_for_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("site_management:exams"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add exam")
        self.assertContains(response, "No exams yet")

    def test_sidebar_exams_section_opens_the_workspace_manager(self):
        self.client.force_login(self.superuser)
        dashboard = self.client.get(reverse("site_management:dashboard"))
        self.assertIn(reverse("site_management:exams"), dashboard.content.decode())

        manager = self.client.get(reverse("site_management:exams"))
        self.assertEqual(manager.status_code, 200)

    def test_exam_create_redirects_to_its_pdf_manager(self):
        self.client.force_login(self.staff)
        response = self._post_exam(title="Delhi Police Constable 2026")

        exam = Exam.objects.get(title="Delhi Police Constable 2026")
        self.assertRedirects(
            response, reverse("site_management:exam_pdfs", args=[exam.pk])
        )
        self.assertEqual(exam.status, Exam.Status.PUBLISHED)

    def test_exam_edit_updates_the_record(self):
        exam = Exam.objects.create(
            title="Old exam title",
            status=Exam.Status.DRAFT,
        )
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("site_management:exam_edit", args=[exam.pk]),
            {
                "title": "New exam title",
                "description": "Updated description.",
                "status": Exam.Status.PUBLISHED,
                "publish_at": "",
                "expires_at": "",
                "sort_order": "3",
                "is_active": "on",
            },
        )

        self.assertRedirects(response, reverse("site_management:exams"))
        exam.refresh_from_db()
        self.assertEqual(exam.title, "New exam title")
        self.assertEqual(exam.status, Exam.Status.PUBLISHED)

    def test_exam_delete_removes_the_exam(self):
        exam = Exam.objects.create(title="Temporary exam", status=Exam.Status.DRAFT)
        self.client.force_login(self.staff)

        confirm = self.client.get(
            reverse("site_management:exam_delete", args=[exam.pk])
        )
        self.assertEqual(confirm.status_code, 200)

        response = self.client.post(
            reverse("site_management:exam_delete", args=[exam.pk])
        )
        self.assertRedirects(response, reverse("site_management:exams"))
        self.assertFalse(Exam.objects.filter(pk=exam.pk).exists())

    def test_exam_pdf_upload_is_stored_and_served_to_the_public(self):
        exam = Exam.objects.create(title="SSC CHSL 2026", status=Exam.Status.PUBLISHED)
        self.client.force_login(self.staff)

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse("site_management:exam_pdf_create", args=[exam.pk]),
                    {
                        "display_name": "Official Notification",
                        "external_link": "",
                        "link_text": "",
                        "sort_order": "0",
                        "is_active": "on",
                        "pdf_file": make_pdf_upload("ssc-chsl.pdf"),
                    },
                )
                self.assertRedirects(
                    response,
                    reverse("site_management:exam_pdfs", args=[exam.pk]),
                )
                pdf = ExamPDF.objects.get(exam=exam)
                self.assertTrue(pdf.pdf_file.name.startswith("cms/exam_pdfs/"))
                self.assertTrue(pdf.pdf_file.storage.exists(pdf.pdf_file.name))
                with pdf.pdf_file.open("rb") as stored_pdf:
                    self.assertEqual(stored_pdf.read(5), b"%PDF-")

            manager = self.client.get(
                reverse("site_management:exam_pdfs", args=[exam.pk])
            )
            self.assertContains(manager, "Official Notification")

        public_page = self.client.get(reverse("accounts:exams"))
        self.assertContains(public_page, "SSC CHSL 2026")
        self.assertContains(public_page, "Official Notification")

    def test_exam_pdf_upload_rejects_renamed_non_pdf(self):
        exam = Exam.objects.create(title="Rejected exam", status=Exam.Status.PUBLISHED)
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("site_management:exam_pdf_create", args=[exam.pk]),
            {
                "display_name": "Fake PDF",
                "external_link": "",
                "link_text": "",
                "sort_order": "0",
                "is_active": "on",
                "pdf_file": make_pdf_upload("fake.pdf", content=b"this is not a pdf"),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid, uncorrupted PDF")
        self.assertFalse(ExamPDF.objects.filter(exam=exam).exists())

    def test_exams_screens_require_staff(self):
        exam = Exam.objects.create(title="Guarded exam", status=Exam.Status.DRAFT)
        for url in (
            reverse("site_management:exams"),
            reverse("site_management:exam_create"),
            reverse("site_management:exam_pdfs", args=[exam.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)

        self.client.force_login(self.member)
        self.assertEqual(
            self.client.get(reverse("site_management:exams")).status_code, 302
        )

    def test_exam_create_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        response = client.post(
            reverse("site_management:exam_create"),
            {
                "title": "No CSRF exam",
                "description": "",
                "status": Exam.Status.PUBLISHED,
                "publish_at": "",
                "expires_at": "",
                "sort_order": "0",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Exam.objects.filter(title="No CSRF exam").exists())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ExamResourceSectionsTests(TestCase):
    """Answer sheets, registration forms, previous papers and results are managed
    inside the workspace and published to their own public pages."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="resourceadmin",
            email="resourceadmin@example.com",
            password="Strongpass123",
        )
        self.staff.is_staff = True
        self.staff.save()
        self.member = User.objects.create_user(
            username="resourcemember",
            email="resourcemember@example.com",
            password="Strongpass123",
        )

    def _result_payload(self, **overrides):
        data = {
            "title": "SSC CGL 2026 Final Result",
            "exam": "",
            "description": "Final result announced.",
            "official_url": "",
            "status": Result.Status.PUBLISHED,
            "published_date": "",
            "sort_order": "0",
            "is_active": "on",
        }
        data.update(overrides)
        return data

    def test_result_requires_an_official_url_or_a_pdf(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("site_management:resource_create", args=["results"]),
            self._result_payload(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Provide an official result URL")
        self.assertFalse(Result.objects.exists())

    def test_result_with_only_an_official_url_is_published_publicly(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("site_management:resource_create", args=["results"]),
            self._result_payload(official_url="https://ssc.gov.in/result"),
        )

        result = Result.objects.get()
        self.assertRedirects(
            response,
            reverse("site_management:resource_detail", args=["results", result.pk]),
        )

        listing = self.client.get(reverse("accounts:results"))
        self.assertContains(listing, "SSC CGL 2026 Final Result")

        detail = self.client.get(reverse("accounts:result_detail", args=[result.pk]))
        self.assertContains(detail, "View Result")
        self.assertContains(detail, "https://ssc.gov.in/result")

    def test_result_with_only_a_pdf_is_stored_and_served_publicly(self):
        self.client.force_login(self.staff)
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse("site_management:resource_create", args=["results"]),
                    {
                        **self._result_payload(),
                        "pdf_file": make_pdf_upload("ssc-result.pdf"),
                    },
                )
                result = Result.objects.get()
                self.assertTrue(result.pdf_file.name.startswith("cms/results/"))
                with result.pdf_file.open("rb") as stored:
                    self.assertEqual(stored.read(5), b"%PDF-")

            self.assertRedirects(
                response,
                reverse("site_management:resource_detail", args=["results", result.pk]),
            )

            detail = self.client.get(
                reverse("accounts:result_detail", args=[result.pk])
            )
            self.assertContains(detail, result.pdf_file.url)
            self.assertContains(detail, "Download result PDF")

    def test_result_rejects_a_renamed_non_pdf(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("site_management:resource_create", args=["results"]),
            {
                **self._result_payload(official_url="https://ssc.gov.in/result"),
                "pdf_file": make_pdf_upload("fake.pdf", content=b"not a real pdf"),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid, uncorrupted PDF")
        self.assertFalse(Result.objects.exists())

    def test_draft_result_is_hidden_from_the_public(self):
        result = Result.objects.create(
            title="Draft result",
            status=Result.Status.DRAFT,
            official_url="https://example.com/result",
        )

        self.assertEqual(
            self.client.get(
                reverse("accounts:result_detail", args=[result.pk])
            ).status_code,
            404,
        )
        listing = self.client.get(reverse("accounts:results"))
        self.assertNotContains(listing, "Draft result")

    def test_future_dated_result_is_hidden_until_its_publication_date(self):
        result = Result.objects.create(
            title="Future result",
            status=Result.Status.PUBLISHED,
            official_url="https://example.com/result",
            published_date=timezone.localdate() + timedelta(days=3),
        )

        self.assertFalse(result.is_published)
        self.assertEqual(
            self.client.get(
                reverse("accounts:result_detail", args=[result.pk])
            ).status_code,
            404,
        )

    def test_toggle_publishes_and_unpublishes_a_result(self):
        result = Result.objects.create(
            title="Toggle result",
            status=Result.Status.DRAFT,
            official_url="https://example.com/result",
        )
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("site_management:resource_toggle", args=["results", result.pk])
        )
        self.assertRedirects(
            response, reverse("site_management:resource_list", args=["results"])
        )
        result.refresh_from_db()
        self.assertEqual(result.status, Result.Status.PUBLISHED)

        self.client.post(
            reverse("site_management:resource_toggle", args=["results", result.pk])
        )
        result.refresh_from_db()
        self.assertEqual(result.status, Result.Status.DRAFT)

    def test_answer_sheet_requires_a_pdf(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("site_management:resource_create", args=["answer-sheets"]),
            {
                "title": "SSC CGL Answer Key",
                "exam": "",
                "description": "",
                "status": AnswerSheet.Status.PUBLISHED,
                "published_date": "",
                "sort_order": "0",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload the answer-sheet PDF.")
        self.assertFalse(AnswerSheet.objects.exists())

    def test_registration_resource_accepts_a_pdf_or_an_official_url(self):
        self.client.force_login(self.staff)
        payload = {
            "title": "Apply online",
            "exam": "",
            "description": "",
            "official_url": "",
            "closing_date": "",
            "status": RegistrationResource.Status.PUBLISHED,
            "published_date": "",
            "sort_order": "0",
            "is_active": "on",
        }

        rejected = self.client.post(
            reverse("site_management:resource_create", args=["registration-forms"]),
            payload,
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertContains(rejected, "Provide an application PDF")

        accepted = self.client.post(
            reverse("site_management:resource_create", args=["registration-forms"]),
            {**payload, "official_url": "https://ssc.gov.in/apply"},
        )
        resource = RegistrationResource.objects.get()
        self.assertRedirects(
            accepted,
            reverse(
                "site_management:resource_detail",
                args=["registration-forms", resource.pk],
            ),
        )

    def test_previous_paper_is_downloadable_from_the_public_page(self):
        self.client.force_login(self.staff)
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.client.post(
                    reverse("site_management:resource_create", args=["previous-papers"]),
                    {
                        "title": "SSC CGL 2024 Paper",
                        "exam": "",
                        "exam_year": "2024",
                        "description": "",
                        "status": PreviousPaper.Status.PUBLISHED,
                        "published_date": "",
                        "sort_order": "0",
                        "is_active": "on",
                        "pdf_file": make_pdf_upload("paper.pdf"),
                    },
                )
            paper = PreviousPaper.objects.get()
            listing = self.client.get(reverse("accounts:previous_papers"))
            self.assertContains(listing, "SSC CGL 2024 Paper")
            self.assertContains(listing, paper.pdf_file.url)

    def test_previous_paper_year_out_of_range_is_rejected(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("site_management:resource_create", args=["previous-papers"]),
            {
                "title": "Bad year paper",
                "exam": "",
                "exam_year": "1800",
                "description": "",
                "status": PreviousPaper.Status.DRAFT,
                "published_date": "",
                "sort_order": "0",
                "is_active": "on",
                "pdf_file": make_pdf_upload("paper.pdf"),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter an exam year between")
        self.assertFalse(PreviousPaper.objects.exists())

    def test_resource_sections_require_staff(self):
        for section in (
            "answer-sheets",
            "registration-forms",
            "previous-papers",
            "results",
        ):
            with self.subTest(section=section):
                self.assertEqual(
                    self.client.get(
                        reverse("site_management:resource_list", args=[section])
                    ).status_code,
                    302,
                )

        self.client.force_login(self.member)
        self.assertEqual(
            self.client.get(
                reverse("site_management:resource_list", args=["results"])
            ).status_code,
            302,
        )

    def test_upcoming_and_recent_exams_are_split_by_exam_date(self):
        today = timezone.localdate()
        Exam.objects.create(
            title="Future SSC exam",
            status=Exam.Status.PUBLISHED,
            exam_date=today + timedelta(days=10),
        )
        Exam.objects.create(
            title="Past SSC exam",
            status=Exam.Status.PUBLISHED,
            exam_date=today - timedelta(days=10),
        )

        upcoming = self.client.get(reverse("accounts:upcoming_exams"))
        self.assertContains(upcoming, "Future SSC exam")
        self.assertNotContains(upcoming, "Past SSC exam")

        recent = self.client.get(reverse("accounts:recent_exams"))
        self.assertContains(recent, "Past SSC exam")
        self.assertNotContains(recent, "Future SSC exam")


@override_settings(
    DEBUG=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class SeedFakeDataCommandTests(TestCase):
    def test_seed_command_is_confirmed_safe_and_idempotent(self):
        from comments.models import Comment
        from jobs.models import Job

        with self.assertRaises(CommandError):
            call_command("seed_fake_data")
        self.assertEqual(Job.objects.count(), 0)

        environment = {
            "SEED_ADMIN_USERNAME": "demo_admin",
            "SEED_ADMIN_EMAIL": "demo-admin@example.com",
            "SEED_ADMIN_PASSWORD": "DemoAdminPass123",
            "SEED_TEST_USERNAME": "demo_candidate",
            "SEED_TEST_EMAIL": "demo-candidate@example.com",
            "SEED_TEST_PASSWORD": "DemoCandidatePass123",
        }
        with patch.dict(os.environ, environment):
            call_command("seed_fake_data", confirm=True, verbosity=0)
            first_counts = {
                "jobs": Job.objects.count(),
                "pages": WebsitePage.objects.count(),
                "sections": ContentSection.objects.count(),
                "items": ContentItem.objects.count(),
                "links": ContentLink.objects.count(),
                "contacts": ContactSubmission.objects.count(),
                "comments": Comment.objects.count(),
                "users": User.objects.count(),
                "settings": WebsiteSettings.objects.count(),
            }
            self.assertEqual(first_counts["jobs"], 24)
            self.assertEqual(Job.objects.filter(status="published").count(), 16)
            self.assertEqual(
                Job.objects.filter(status="published", is_verified=True).count(),
                0,
            )
            self.assertEqual(first_counts["pages"], 6)
            self.assertEqual(first_counts["contacts"], 3)
            self.assertEqual(first_counts["comments"], 3)
            self.assertEqual(first_counts["users"], 2)
            self.assertEqual(first_counts["settings"], 1)
            self.assertTrue(
                Job.objects.filter(
                    status="published",
                    is_verified=False,
                    title__startswith="DEMO ONLY:",
                ).exists()
            )
            self.assertTrue(
                User.objects.get(username="demo_admin").is_superuser
            )

            call_command("seed_fake_data", confirm=True, verbosity=0)

        second_counts = {
            "jobs": Job.objects.count(),
            "pages": WebsitePage.objects.count(),
            "sections": ContentSection.objects.count(),
            "items": ContentItem.objects.count(),
            "links": ContentLink.objects.count(),
            "contacts": ContactSubmission.objects.count(),
            "comments": Comment.objects.count(),
            "users": User.objects.count(),
            "settings": WebsiteSettings.objects.count(),
        }
        self.assertEqual(second_counts, first_counts)

    def test_seed_command_skips_account_dependent_data_without_credentials(self):
        from comments.models import Comment
        from jobs.models import Job

        empty_credentials = {
            key: ""
            for names in (
                "SEED_ADMIN_USERNAME SEED_ADMIN_EMAIL SEED_ADMIN_PASSWORD",
                "SEED_TEST_USERNAME SEED_TEST_EMAIL SEED_TEST_PASSWORD",
            )
            for key in names.split()
        }
        with patch.dict(os.environ, empty_credentials):
            call_command("seed_fake_data", confirm=True, verbosity=0)

        self.assertEqual(Job.objects.count(), 24)
        self.assertEqual(Comment.objects.count(), 0)
        self.assertEqual(User.objects.count(), 0)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ResourceURLTests(TestCase):
    """Tests for the ResourceURL model and formset functionality."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="resourceadmin",
            email="resourceadmin@example.com",
            password="Strongpass123",
        )
        self.staff.is_staff = True
        self.staff.save()

    def _previous_paper_payload(self, **overrides):
        data = {
            "title": "SSC CGL 2023 Previous Paper",
            "exam": "",
            "description": "Previous year question paper.",
            "exam_year": "2023",
            "status": PreviousPaper.Status.PUBLISHED,
            "published_date": "",
            "sort_order": "0",
            "is_active": "on",
        }
        data.update(overrides)
        return data

    def test_resource_url_validation_rejects_dangerous_schemes(self):
        """Test that ResourceURL validation rejects javascript:, data:, and other dangerous schemes."""
        self.client.force_login(self.staff)

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse("site_management:resource_create", args=["previous-papers"]),
                    {
                        **self._previous_paper_payload(),
                        "pdf_file": make_pdf_upload("paper.pdf"),
                        "resource_urls-TOTAL_FORMS": "1",
                        "resource_urls-INITIAL_FORMS": "0",
                        "resource_urls-MIN_NUM_FORMS": "0",
                        "resource_urls-MAX_NUM_FORMS": "1000",
                        "resource_urls-0-label": "Dangerous link",
                        "resource_urls-0-url": "javascript:alert('xss')",
                        "resource_urls-0-target": "new",
                        "resource_urls-0-sort_order": "0",
                        "resource_urls-0-is_active": "on",
                    },
                )
                self.assertEqual(response.status_code, 200)
                # Check that the form has errors
                self.assertFalse(response.context["url_formset"].is_valid())
                # Check that the specific form has a URL field error
                form = response.context["url_formset"].forms[0]
                self.assertIn("url", form.errors)
                self.assertIn("This URL scheme is not allowed for security reasons.", str(form.errors["url"]))

    def test_resource_url_validation_rejects_data_scheme(self):
        """Test that ResourceURL validation rejects data: URLs."""
        self.client.force_login(self.staff)

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse("site_management:resource_create", args=["previous-papers"]),
                    {
                        **self._previous_paper_payload(),
                        "pdf_file": make_pdf_upload("paper.pdf"),
                        "resource_urls-TOTAL_FORMS": "1",
                        "resource_urls-INITIAL_FORMS": "0",
                        "resource_urls-MIN_NUM_FORMS": "0",
                        "resource_urls-MAX_NUM_FORMS": "1000",
                        "resource_urls-0-label": "Data link",
                        "resource_urls-0-url": "data:text/html,<script>alert('xss')</script>",
                        "resource_urls-0-target": "new",
                        "resource_urls-0-sort_order": "0",
                        "resource_urls-0-is_active": "on",
                    },
                )
                self.assertEqual(response.status_code, 200)
                # Check that the form has errors
                self.assertFalse(response.context["url_formset"].is_valid())
                # Check that the specific form has a URL field error
                form = response.context["url_formset"].forms[0]
                self.assertIn("url", form.errors)
                self.assertIn("This URL scheme is not allowed for security reasons.", str(form.errors["url"]))

    def test_resource_url_accepts_valid_http_https_urls(self):
        """Test that ResourceURL accepts valid HTTP/HTTPS URLs."""
        self.client.force_login(self.staff)

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse("site_management:resource_create", args=["previous-papers"]),
                    {
                        **self._previous_paper_payload(),
                        "pdf_file": make_pdf_upload("paper.pdf"),
                        "resource_urls-TOTAL_FORMS": "1",
                        "resource_urls-INITIAL_FORMS": "0",
                        "resource_urls-MIN_NUM_FORMS": "0",
                        "resource_urls-MAX_NUM_FORMS": "1000",
                        "resource_urls-0-label": "Official Website",
                        "resource_urls-0-url": "https://example.org/official",
                        "resource_urls-0-target": "new",
                        "resource_urls-0-sort_order": "0",
                        "resource_urls-0-is_active": "on",
                    },
                )
                self.assertEqual(response.status_code, 302)
                paper = PreviousPaper.objects.get()
                self.assertEqual(paper.resource_urls.count(), 1)
                self.assertEqual(paper.resource_urls.first().label, "Official Website")
                self.assertEqual(paper.resource_urls.first().url, "https://example.org/official")

    def test_resource_url_accepts_internal_paths(self):
        """Test that ResourceURL accepts internal paths starting with /."""
        self.client.force_login(self.staff)

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse("site_management:resource_create", args=["previous-papers"]),
                    {
                        **self._previous_paper_payload(),
                        "pdf_file": make_pdf_upload("paper.pdf"),
                        "resource_urls-TOTAL_FORMS": "1",
                        "resource_urls-INITIAL_FORMS": "0",
                        "resource_urls-MIN_NUM_FORMS": "0",
                        "resource_urls-MAX_NUM_FORMS": "1000",
                        "resource_urls-0-label": "Related Page",
                        "resource_urls-0-url": "/exam-details/123",
                        "resource_urls-0-target": "same",
                        "resource_urls-0-sort_order": "0",
                        "resource_urls-0-is_active": "on",
                    },
                )
                self.assertEqual(response.status_code, 302)
                paper = PreviousPaper.objects.get()
                self.assertEqual(paper.resource_urls.count(), 1)
                self.assertEqual(paper.resource_urls.first().url, "/exam-details/123")
                self.assertEqual(paper.resource_urls.first().target, "same")

    def test_multiple_resource_urls_can_be_saved(self):
        """Test that multiple ResourceURLs can be saved to a single resource."""
        self.client.force_login(self.staff)

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse("site_management:resource_create", args=["previous-papers"]),
                    {
                        **self._previous_paper_payload(),
                        "pdf_file": make_pdf_upload("paper.pdf"),
                        "resource_urls-TOTAL_FORMS": "3",
                        "resource_urls-INITIAL_FORMS": "0",
                        "resource_urls-MIN_NUM_FORMS": "0",
                        "resource_urls-MAX_NUM_FORMS": "1000",
                        "resource_urls-0-label": "Official Website",
                        "resource_urls-0-url": "https://example.org/official",
                        "resource_urls-0-target": "new",
                        "resource_urls-0-sort_order": "0",
                        "resource_urls-0-is_active": "on",
                        "resource_urls-1-label": "Apply Online",
                        "resource_urls-1-url": "https://example.org/apply",
                        "resource_urls-1-target": "new",
                        "resource_urls-1-sort_order": "1",
                        "resource_urls-1-is_active": "on",
                        "resource_urls-2-label": "Download Notification",
                        "resource_urls-2-url": "https://example.org/notification.pdf",
                        "resource_urls-2-target": "new",
                        "resource_urls-2-sort_order": "2",
                        "resource_urls-2-is_active": "on",
                    },
                )
                self.assertEqual(response.status_code, 302)
                paper = PreviousPaper.objects.get()
                self.assertEqual(paper.resource_urls.count(), 3)
                labels = [url.label for url in paper.resource_urls.all()]
                self.assertIn("Official Website", labels)
                self.assertIn("Apply Online", labels)
                self.assertIn("Download Notification", labels)

    def test_resource_urls_can_be_edited(self):
        """Test that ResourceURLs can be edited via the formset."""
        self.client.force_login(self.staff)

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                # Create a paper with one URL
                create_response = self.client.post(
                    reverse("site_management:resource_create", args=["previous-papers"]),
                    {
                        **self._previous_paper_payload(),
                        "pdf_file": make_pdf_upload("paper.pdf"),
                        "resource_urls-TOTAL_FORMS": "1",
                        "resource_urls-INITIAL_FORMS": "0",
                        "resource_urls-MIN_NUM_FORMS": "0",
                        "resource_urls-MAX_NUM_FORMS": "1000",
                        "resource_urls-0-label": "Old Label",
                        "resource_urls-0-url": "https://example.org/old",
                        "resource_urls-0-target": "new",
                        "resource_urls-0-sort_order": "0",
                        "resource_urls-0-is_active": "on",
                    },
                )
                paper = PreviousPaper.objects.get()
                self.assertEqual(paper.resource_urls.count(), 1)

                # Edit the URL
                edit_response = self.client.post(
                    reverse("site_management:resource_edit", args=["previous-papers", paper.pk]),
                    {
                        **self._previous_paper_payload(title=paper.title),
                        "resource_urls-TOTAL_FORMS": "1",
                        "resource_urls-INITIAL_FORMS": "0",
                        "resource_urls-MIN_NUM_FORMS": "0",
                        "resource_urls-MAX_NUM_FORMS": "1000",
                        "resource_urls-0-label": "New Label",
                        "resource_urls-0-url": "https://example.org/new",
                        "resource_urls-0-target": "same",
                        "resource_urls-0-sort_order": "0",
                        "resource_urls-0-is_active": "on",
                    },
                )
                self.assertEqual(edit_response.status_code, 302)
                paper.refresh_from_db()
                self.assertEqual(paper.resource_urls.count(), 1)
                self.assertEqual(paper.resource_urls.first().label, "New Label")
                self.assertEqual(paper.resource_urls.first().url, "https://example.org/new")
                self.assertEqual(paper.resource_urls.first().target, "same")

    def test_resource_urls_can_be_deleted(self):
        """Test that ResourceURLs can be deleted via the formset DELETE checkbox."""
        self.client.force_login(self.staff)

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                # Create a paper with two URLs
                create_response = self.client.post(
                    reverse("site_management:resource_create", args=["previous-papers"]),
                    {
                        **self._previous_paper_payload(),
                        "pdf_file": make_pdf_upload("paper.pdf"),
                        "resource_urls-TOTAL_FORMS": "2",
                        "resource_urls-INITIAL_FORMS": "0",
                        "resource_urls-MIN_NUM_FORMS": "0",
                        "resource_urls-MAX_NUM_FORMS": "1000",
                        "resource_urls-0-label": "URL 1",
                        "resource_urls-0-url": "https://example.org/1",
                        "resource_urls-0-target": "new",
                        "resource_urls-0-sort_order": "0",
                        "resource_urls-0-is_active": "on",
                        "resource_urls-1-label": "URL 2",
                        "resource_urls-1-url": "https://example.org/2",
                        "resource_urls-1-target": "new",
                        "resource_urls-1-sort_order": "1",
                        "resource_urls-1-is_active": "on",
                    },
                )
                paper = PreviousPaper.objects.get()
                self.assertEqual(paper.resource_urls.count(), 2)

                # Delete one URL
                edit_response = self.client.post(
                    reverse("site_management:resource_edit", args=["previous-papers", paper.pk]),
                    {
                        **self._previous_paper_payload(title=paper.title),
                        "resource_urls-TOTAL_FORMS": "2",
                        "resource_urls-INITIAL_FORMS": "0",
                        "resource_urls-MIN_NUM_FORMS": "0",
                        "resource_urls-MAX_NUM_FORMS": "1000",
                        "resource_urls-0-label": "URL 1",
                        "resource_urls-0-url": "https://example.org/1",
                        "resource_urls-0-target": "new",
                        "resource_urls-0-sort_order": "0",
                        "resource_urls-0-is_active": "on",
                        "resource_urls-0-DELETE": "on",
                        "resource_urls-1-label": "URL 2",
                        "resource_urls-1-url": "https://example.org/2",
                        "resource_urls-1-target": "new",
                        "resource_urls-1-sort_order": "1",
                        "resource_urls-1-is_active": "on",
                    },
                )
                self.assertEqual(edit_response.status_code, 302)
                paper.refresh_from_db()
                self.assertEqual(paper.resource_urls.count(), 1)
                self.assertEqual(paper.resource_urls.first().label, "URL 2")

    def test_resource_urls_render_on_public_detail_page(self):
        """Test that ResourceURLs render correctly on the public detail page."""
        self.client.force_login(self.staff)

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.client.post(
                    reverse("site_management:resource_create", args=["previous-papers"]),
                    {
                        **self._previous_paper_payload(title="Test Paper"),
                        "pdf_file": make_pdf_upload("paper.pdf"),
                        "resource_urls-TOTAL_FORMS": "2",
                        "resource_urls-INITIAL_FORMS": "0",
                        "resource_urls-MIN_NUM_FORMS": "0",
                        "resource_urls-MAX_NUM_FORMS": "1000",
                        "resource_urls-0-label": "Official Website",
                        "resource_urls-0-url": "https://example.org/official",
                        "resource_urls-0-target": "new",
                        "resource_urls-0-sort_order": "0",
                        "resource_urls-0-is_active": "on",
                        "resource_urls-1-label": "Internal Link",
                        "resource_urls-1-url": "/exam-details/123",
                        "resource_urls-1-target": "same",
                        "resource_urls-1-sort_order": "1",
                        "resource_urls-1-is_active": "on",
                    },
                )
                paper = PreviousPaper.objects.get()
                paper.status = PreviousPaper.Status.PUBLISHED
                paper.published_date = timezone.localdate()
                paper.save()

                # Check public detail page
                detail_response = self.client.get(
                    reverse("accounts:previous_paper_detail", args=[paper.pk])
                )
                self.assertContains(detail_response, "Official Website")
                self.assertContains(detail_response, "https://example.org/official")
                self.assertContains(detail_response, "Internal Link")
                self.assertContains(detail_response, "/exam-details/123")
                self.assertContains(detail_response, "Additional Links")

    def test_resource_urls_render_on_public_list_page(self):
        """Test that ResourceURLs render correctly on the public list page."""
        self.client.force_login(self.staff)

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.client.post(
                    reverse("site_management:resource_create", args=["previous-papers"]),
                    {
                        **self._previous_paper_payload(title="Test Paper"),
                        "pdf_file": make_pdf_upload("paper.pdf"),
                        "resource_urls-TOTAL_FORMS": "1",
                        "resource_urls-INITIAL_FORMS": "0",
                        "resource_urls-MIN_NUM_FORMS": "0",
                        "resource_urls-MAX_NUM_FORMS": "1000",
                        "resource_urls-0-label": "Quick Link",
                        "resource_urls-0-url": "https://example.org/quick",
                        "resource_urls-0-target": "new",
                        "resource_urls-0-sort_order": "0",
                        "resource_urls-0-is_active": "on",
                    },
                )
                paper = PreviousPaper.objects.get()
                paper.status = PreviousPaper.Status.PUBLISHED
                paper.published_date = timezone.localdate()
                paper.save()

                # Check public list page
                list_response = self.client.get(reverse("accounts:previous_papers"))
                self.assertContains(list_response, "Quick Link")
                self.assertContains(list_response, "https://example.org/quick")

    def test_inactive_resource_urls_do_not_render(self):
        """Test that inactive ResourceURLs do not render on public pages."""
        self.client.force_login(self.staff)

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.client.post(
                    reverse("site_management:resource_create", args=["previous-papers"]),
                    {
                        **self._previous_paper_payload(title="Test Paper"),
                        "pdf_file": make_pdf_upload("paper.pdf"),
                        "resource_urls-TOTAL_FORMS": "2",
                        "resource_urls-INITIAL_FORMS": "0",
                        "resource_urls-MIN_NUM_FORMS": "0",
                        "resource_urls-MAX_NUM_FORMS": "1000",
                        "resource_urls-0-label": "Active Link",
                        "resource_urls-0-url": "https://example.org/active",
                        "resource_urls-0-target": "new",
                        "resource_urls-0-sort_order": "0",
                        "resource_urls-0-is_active": "on",
                        "resource_urls-1-label": "Inactive Link",
                        "resource_urls-1-url": "https://example.org/inactive",
                        "resource_urls-1-target": "new",
                        "resource_urls-1-sort_order": "1",
                        "resource_urls-1-is_active": "",
                    },
                )
                paper = PreviousPaper.objects.get()
                paper.status = PreviousPaper.Status.PUBLISHED
                paper.published_date = timezone.localdate()
                paper.save()

                # Check that only active URL renders
                detail_response = self.client.get(
                    reverse("accounts:previous_paper_detail", args=[paper.pk])
                )
                self.assertContains(detail_response, "Active Link")
                self.assertNotContains(detail_response, "Inactive Link")
