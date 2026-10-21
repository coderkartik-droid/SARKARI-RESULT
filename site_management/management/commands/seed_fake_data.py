import os
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from comments.models import Comment
from jobs.models import Job, JobAgeRelaxation
from site_management.models import (
    ContactSubmission,
    ContentItem,
    ContentLink,
    ContentSection,
    WebsitePage,
    WebsiteSettings,
)


ACCOUNT_ENVIRONMENT_KEYS = {
    "admin": (
        "SEED_ADMIN_USERNAME",
        "SEED_ADMIN_EMAIL",
        "SEED_ADMIN_PASSWORD",
    ),
    "test": (
        "SEED_TEST_USERNAME",
        "SEED_TEST_EMAIL",
        "SEED_TEST_PASSWORD",
    ),
}

DEMO_JOBS = (
    ("Latest Jobs", "State Civil Services Officer Recruitment 2026", "Demo State Public Service Board", "Graduate", "All India", 420, 21, 32, "graduate"),
    ("Latest Jobs", "Junior Secretariat Assistant Recruitment 2026", "Demo National Administration Commission", "12th Pass", "Delhi", 185, 18, 27, "12th"),
    ("Latest Jobs", "Technical Assistant Recruitment 2026", "Demo Public Science Council", "Diploma / BSc", "Madhya Pradesh", 96, 18, 30, "diploma"),
    ("Latest Jobs", "Community Health Officer Recruitment 2026", "Demo State Health Services Board", "BSc Nursing", "Rajasthan", 310, 21, 35, "graduate"),
    ("Admit Cards", "Graduate Level Examination Admit Card 2026", "Demo Staff Selection Board", "Graduate", "All India", 1, 18, 30, "graduate"),
    ("Admit Cards", "Assistant Engineer Screening Test Admit Card 2026", "Demo Infrastructure Recruitment Council", "Engineering Degree", "Uttar Pradesh", 1, 21, 35, "graduate"),
    ("Admit Cards", "Police Constable Written Exam Admit Card 2026", "Demo State Police Recruitment Board", "12th Pass", "Bihar", 1, 18, 25, "12th"),
    ("Admit Cards", "Technical Apprentice Exam City Notice 2026", "Demo National Skills Directorate", "ITI", "All India", 1, 18, 28, "iti"),
    ("Answer Keys", "Combined Eligibility Test Provisional Answer Key 2026", "Demo Examination Services Commission", "Graduate", "All India", 1, 18, 32, "graduate"),
    ("Answer Keys", "Junior Engineer Recruitment Answer Key 2026", "Demo Public Works Selection Board", "Diploma", "Haryana", 1, 18, 30, "diploma"),
    ("Answer Keys", "Teaching Assistant Written Test Answer Key 2026", "Demo Education Staffing Council", "Graduate", "Jharkhand", 1, 21, 40, "graduate"),
    ("Answer Keys", "Clerical Aptitude Examination Response Sheet 2026", "Demo Administrative Exams Bureau", "12th Pass", "All India", 1, 18, 27, "12th"),
    ("Admissions", "Public University Undergraduate Admissions 2026", "Demo Central Learning University", "12th Pass", "All India", 2400, 16, 25, "12th"),
    ("Admissions", "Diploma in Public Health Admissions 2026", "Demo Institute of Community Health", "12th Pass", "Kerala", 180, 17, 28, "12th"),
    ("Admissions", "Government Polytechnic Lateral Entry Admissions 2026", "Demo Technical Education Council", "Diploma", "Gujarat", 650, 18, 30, "diploma"),
    ("Admissions", "Public Policy Postgraduate Programme Admissions 2026", "Demo School of Governance", "Graduate", "All India", 120, 20, 32, "graduate"),
    ("Syllabus", "Administrative Officer Examination Syllabus 2026", "Demo Civil Services Examination Board", "Graduate", "All India", 1, 21, 32, "graduate"),
    ("Syllabus", "Technical Instructor Examination Pattern and Syllabus 2026", "Demo Vocational Education Authority", "ITI / Diploma", "Punjab", 1, 18, 30, "iti"),
    ("Syllabus", "Public School Teacher Eligibility Syllabus 2026", "Demo Teacher Standards Council", "Graduate", "Odisha", 1, 21, 40, "graduate"),
    ("Syllabus", "Junior Accounts Assistant Exam Scheme 2026", "Demo Public Finance Recruitment Board", "Graduate", "All India", 1, 18, 30, "graduate"),
    ("Certificate Verification", "Document Verification Schedule for Clerk Recruitment 2026", "Demo Regional Recruitment Office", "Graduate", "Maharashtra", 220, 18, 30, "graduate"),
    ("Certificate Verification", "Certificate Scrutiny Notice for Lab Assistant Posts 2026", "Demo Public Research Staffing Board", "BSc", "Tamil Nadu", 74, 18, 32, "graduate"),
    ("Certificate Verification", "Original Document Check for Junior Engineer Posts 2026", "Demo State Engineering Services Board", "Diploma", "Uttarakhand", 58, 18, 35, "diploma"),
    ("Certificate Verification", "Eligibility Certificate Verification for Support Staff 2026", "Demo District Services Commission", "10th / 12th Pass", "Assam", 135, 18, 27, "10th"),
)

DEMO_CMS_SECTIONS = (
    (
        "demo-results",
        "DEMO ONLY: Results",
        "Illustrative result cards for local development and layout review.",
        "result",
        "Results",
        (
            ("DEMO ONLY: Graduate Screening Test scorecard", "A sample result notice showing where a scorecard and merit-list summary could appear."),
            ("DEMO ONLY: Junior Assistant shortlist", "Illustrative shortlist content. Confirm all result details with the issuing authority."),
        ),
    ),
    (
        "demo-admit-cards",
        "DEMO ONLY: Admit Cards",
        "Illustrative exam-day notices for local development.",
        "ticket",
        "Admit Cards",
        (
            ("DEMO ONLY: Screening test hall ticket", "Sample admit-card release information and exam-day instructions."),
            ("DEMO ONLY: Exam city information slip", "A placeholder card for a verified examination city notice."),
        ),
    ),
    (
        "demo-answer-keys",
        "DEMO ONLY: Answer Keys",
        "Illustrative answer-key and objection notices.",
        "key",
        "Answer Keys",
        (
            ("DEMO ONLY: Provisional answer key released", "Sample notice explaining how candidates might review a provisional key."),
            ("DEMO ONLY: Objection window information", "Illustrative objection-window card; no real examination or deadline is represented."),
        ),
    ),
    (
        "demo-admissions",
        "DEMO ONLY: Admissions",
        "Illustrative admission notices for the public content layout.",
        "graduation-cap",
        "Admissions",
        (
            ("DEMO ONLY: Undergraduate application guide", "A sample admission card for demonstrating course, eligibility, and application links."),
            ("DEMO ONLY: Diploma counselling schedule", "Placeholder counselling information for local UI review only."),
        ),
    ),
    (
        "demo-syllabus",
        "DEMO ONLY: Syllabus",
        "Illustrative syllabus and exam-pattern cards.",
        "book",
        "Syllabus",
        (
            ("DEMO ONLY: Administrative services exam pattern", "A sample syllabus card demonstrating a structured exam resource."),
            ("DEMO ONLY: Technical instructor subject outline", "Placeholder subject-outline content; consult an official notice for real requirements."),
        ),
    ),
    (
        "demo-certificate-verification",
        "DEMO ONLY: Certificate Verification",
        "Illustrative document-verification notices.",
        "file-check",
        "Certificate Verification",
        (
            ("DEMO ONLY: Document scrutiny schedule", "Sample verification-stage card with a reminder to bring original certificates."),
            ("DEMO ONLY: Candidate document checklist", "Illustrative checklist for preview purposes; it is not an official instruction."),
        ),
    ),
)

DEMO_PAGES = (
    (
        WebsitePage.PageType.ABOUT_US,
        "DEMO ONLY: About Us",
        "Illustrative information page",
        "This demonstration page shows where administrators can describe the website. It is sample content, not an official government communication.",
    ),
    (
        WebsitePage.PageType.CONTACT_US,
        "DEMO ONLY: Contact Us",
        "Illustrative contact page",
        "This demonstration page uses reserved example contact details. Replace them with verified site contact information before launch.",
    ),
    (
        WebsitePage.PageType.PRIVACY_POLICY,
        "DEMO ONLY: Privacy Policy",
        "Placeholder — review before publication",
        "This is placeholder demonstration text and is not legal advice or a complete privacy policy. Replace it with a policy reviewed for your actual data practices before publishing.",
    ),
    (
        WebsitePage.PageType.TERMS_AND_CONDITIONS,
        "DEMO ONLY: Terms and Conditions",
        "Placeholder — review before publication",
        "This is placeholder demonstration text and is not legal advice or complete terms. Replace it with terms reviewed for your actual service before publishing.",
    ),
    (
        WebsitePage.PageType.DISCLAIMER,
        "DEMO ONLY: Disclaimer",
        "Illustrative information",
        "All seeded listings and notices are fictional examples for development. They are not verified opportunities, official notices, or government advice.",
    ),
    (
        WebsitePage.PageType.CONTENT_DETAILS,
        "DEMO ONLY: Content Details",
        "Illustrative content information",
        "This sample page demonstrates the editable content-details route. It contains no official listings or verified information.",
    ),
)

DEMO_CONTACTS = (
    ("Demo Visitor", "+91 90000 00001", "visitor@example.com", "DEMO ONLY: Question about a sample listing", "This is a fictional contact message for testing the staff inbox. No reply is required."),
    ("Sample Candidate", "+91 90000 00002", "candidate@example.com", "DEMO ONLY: Update on sample exam notice", "Placeholder inquiry for checking message details and unread status in development."),
    ("Preview User", "+91 90000 00003", "preview@example.com", "DEMO ONLY: Website feedback", "Sample feedback used to preview contact-message management. This is not from a real visitor."),
)

DEMO_COMMENTS = (
    ("DEMO ONLY: The sample exam-pattern card is easy to follow.", Comment.Status.PUBLISHED),
    ("DEMO ONLY: Please add a placeholder for an official notification link.", Comment.Status.PENDING),
    ("DEMO ONLY: This rejected comment is present to preview moderation states.", Comment.Status.REJECTED),
)


class Command(BaseCommand):
    help = "Add clearly marked, idempotent development/demo data without overwriting existing records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm that demo records should be added to the configured development database.",
        )

    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError(
                "No data was added. Re-run with --confirm after checking the configured database."
            )
        if not settings.DEBUG:
            raise CommandError(
                "Refusing to seed data while DEBUG is False. Use development settings only."
            )

        account_config = self._account_config()
        User = get_user_model()
        today = timezone.localdate()
        counts = {
            "jobs": 0,
            "age_relaxations": 0,
            "pages": 0,
            "sections": 0,
            "content_items": 0,
            "content_links": 0,
            "contacts": 0,
            "comments": 0,
            "users": 0,
            "website_settings": 0,
        }

        with transaction.atomic():
            users = self._seed_users(User, account_config, counts)
            _, settings_created = WebsiteSettings.objects.get_or_create(
                pk=1,
                defaults={
                    "site_name": "Sarkari Result — Demo",
                    "tagline": "Fictional sample content for development",
                    "logo_text": "DEMO",
                    "header_text": "DEVELOPMENT PREVIEW",
                    "hero_title": "A preview of the public information portal",
                    "hero_description": (
                        "This local development site contains clearly marked, "
                        "fictional sample listings. Verify official sources before use."
                    ),
                    "announcement": (
                        "DEMO SITE: All seeded job notices, results, and messages are fictional."
                    ),
                    "hero_note_title": "Demonstration data",
                    "hero_note_body": (
                        "Examples are provided for layout and workflow testing only. "
                        "They are not official opportunities or verified notices."
                    ),
                    "hero_note_footer": "Replace or remove all demo content before deployment.",
                    "footer_description": "Development preview populated with fictional sample content.",
                    "footer_contact": "Reserved demo contact details only.",
                    "footer_disclaimer": "DEMO DATA ONLY — verify official sources.",
                },
            )
            counts["website_settings"] += int(settings_created)
            self._seed_pages(counts)
            self._seed_cms(counts)
            self._seed_jobs(today, counts)
            self._seed_contacts(counts)
            if users.get("test"):
                self._seed_comments(users["test"], counts)

        self.stdout.write(self.style.SUCCESS("Demo data seeding completed."))
        for name, count in counts.items():
            self.stdout.write(f"  {name.replace('_', ' ').title()}: {count} added")
        if not users:
            self.stdout.write(
                "  Login accounts: skipped because no seed account credentials are configured."
            )
        if users.get("test") is None:
            self.stdout.write(
                "  Comments: skipped because SEED_TEST_USERNAME, SEED_TEST_EMAIL, "
                "and SEED_TEST_PASSWORD are not all configured."
            )
        self.stdout.write(
            "  Existing rows were left unchanged. Seeded Job records are unverified "
            "and therefore remain excluded from public verified-job results."
        )

    def _account_config(self):
        configured = {
            role: tuple(
                os.environ.get(key, "").strip()
                if "PASSWORD" not in key
                else os.environ.get(key, "")
                for key in keys
            )
            for role, keys in ACCOUNT_ENVIRONMENT_KEYS.items()
        }
        for role, values in configured.items():
            if any(values) and not all(values):
                raise CommandError(
                    f"Configure all three environment variables for the {role} account, or leave all three unset."
                )
        result = {
            role: dict(zip(("username", "email", "password"), values))
            for role, values in configured.items()
            if all(values)
        }
        if result.get("admin") and result.get("test") and (
            result["admin"]["username"].casefold()
            == result["test"]["username"].casefold()
            or result["admin"]["email"].casefold()
            == result["test"]["email"].casefold()
        ):
            raise CommandError("The admin and test accounts must use distinct usernames and emails.")
        return result

    def _seed_users(self, User, account_config, counts):
        users = {}
        for role, values in account_config.items():
            username = values["username"].casefold()
            email = values["email"].casefold()
            existing = User.objects.filter(username__iexact=username).first()
            existing_by_email = User.objects.filter(email__iexact=email).first()
            if existing and existing.email.casefold() != email:
                raise CommandError(f"The configured {role} username is already in use.")
            if existing_by_email and existing_by_email.pk != getattr(existing, "pk", None):
                raise CommandError(f"The configured {role} email is already in use.")

            if existing:
                user = existing
                if role == "admin" and not (user.is_staff and user.is_superuser):
                    raise CommandError(
                        "The configured admin account exists but is not already a superuser; "
                        "the seed command will not elevate an existing account."
                    )
            else:
                user = User(username=username, email=email, full_name=username)
                try:
                    validate_password(values["password"], user=user)
                except ValidationError as error:
                    raise CommandError(
                        f"The configured {role} password does not meet the active password policy."
                    ) from error
                if role == "admin":
                    user = User.objects.create_superuser(
                        username=username,
                        email=email,
                        password=values["password"],
                        full_name=username,
                    )
                else:
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=values["password"],
                        full_name=username,
                    )
                counts["users"] += 1
            users[role] = user
        return users

    def _seed_pages(self, counts):
        for page_type, title, subtitle, description in DEMO_PAGES:
            defaults = {
                "title": title,
                "subtitle": subtitle,
                "description": description,
                "is_published": True,
            }
            if page_type == WebsitePage.PageType.CONTACT_US:
                defaults.update(
                    {
                        "contact_email": "demo-contact@example.com",
                        "contact_intro": (
                            "DEMO ONLY: Use this page to preview the contact form. "
                            "Replace this reserved address before launch."
                        ),
                    }
                )
            _, created = WebsitePage.objects.get_or_create(
                page_type=page_type,
                defaults=defaults,
            )
            counts["pages"] += int(created)

    def _seed_cms(self, counts):
        sections = {}
        announcements, created = ContentSection.objects.get_or_create(
            slug="demo-announcements",
            defaults={
                "area": ContentSection.Area.ANNOUNCEMENTS,
                "title": "DEMO ONLY: Notices",
                "description": "Fictional notices for local preview.",
                "sort_order": 0,
                "is_active": True,
            },
        )
        if (
            announcements.area != ContentSection.Area.ANNOUNCEMENTS
            or announcements.title != "DEMO ONLY: Notices"
        ):
            raise CommandError(
                "The demo-announcements slug is already used by non-demo content."
            )
        sections["announcements"] = announcements
        counts["sections"] += int(created)
        for slug, title, description, icon, _label, _items in DEMO_CMS_SECTIONS:
            section, created = ContentSection.objects.get_or_create(
                slug=slug,
                defaults={
                    "area": ContentSection.Area.HOMEPAGE,
                    "title": title,
                    "description": description,
                    "icon": icon,
                    "sort_order": 100 + len(sections) * 10,
                    "is_active": True,
                },
            )
            if (
                section.area != ContentSection.Area.HOMEPAGE
                or section.title != title
            ):
                raise CommandError(
                    f"The {slug} slug is already used by non-demo content."
                )
            sections[slug] = section
            counts["sections"] += int(created)

        for slug, _title, _description, icon, _label, items in DEMO_CMS_SECTIONS:
            section = sections[slug]
            for index, (item_label, body) in enumerate(items):
                item, created = ContentItem.objects.get_or_create(
                    section=section,
                    label=item_label,
                    defaults={
                        "body": body,
                        "short_description": body,
                        "icon": icon,
                        "sort_order": index * 10,
                        "is_active": True,
                        "show_on_homepage": True,
                        "is_featured": index == 0,
                        "button_text": "View demo section",
                        "button_url": f"/accounts/sections/{slug}/",
                    },
                )
                counts["content_items"] += int(created)
                _, link_created = ContentLink.objects.get_or_create(
                    content_item=item,
                    label="Open demo section",
                    defaults={
                        "url": f"/accounts/sections/{slug}/",
                        "description": "Open the clearly marked demonstration section.",
                        "display_order": 0,
                        "is_active": True,
                    },
                )
                counts["content_links"] += int(link_created)

        announcement = "DEMO ONLY: Sample notices are fictional; verify all information with official sources."
        announcement_item, created = ContentItem.objects.get_or_create(
            section=announcements,
            label="DEMO ONLY: Development preview notice",
            defaults={
                "body": announcement,
                "short_description": announcement,
                "sort_order": 0,
                "is_active": True,
                "show_on_homepage": True,
            },
        )
        counts["content_items"] += int(created)
        _, link_created = ContentLink.objects.get_or_create(
            content_item=announcement_item,
            label="Browse sample jobs",
            defaults={
                "url": "/jobs/",
                "description": "Open the development jobs listing.",
                "display_order": 0,
                "is_active": True,
            },
        )
        counts["content_links"] += int(link_created)

    def _seed_jobs(self, today, counts):
        for index, values in enumerate(DEMO_JOBS):
            category, title, organization, qualification, location, vacancies, min_age, max_age, min_qualification = values
            status = "published" if index < 16 else "draft" if index < 20 else "archived"
            start_date = today - timedelta(days=2)
            end_date = today + timedelta(days=21 + index) if status != "archived" else today - timedelta(days=30 + index)
            job, created = Job.objects.get_or_create(
                title=f"DEMO ONLY: {title}",
                defaults={
                    "organization": organization,
                    "qualification": qualification,
                    "min_qualification": min_qualification,
                    "location": location,
                    "category": category,
                    "vacancies_count": vacancies,
                    "min_age": min_age,
                    "max_age": max_age,
                    "age_cutoff_date": today + timedelta(days=30),
                    "application_start_date": start_date,
                    "application_end_date": end_date,
                    "official_notification_url": "https://example.org/demo/notification",
                    "application_url": "https://example.org/demo/application",
                    "source_url": "https://example.org/demo",
                    "last_verified_date": None,
                    "status": status,
                    "is_verified": False,
                    "is_expired": status == "archived",
                },
            )
            counts["jobs"] += int(created)
            if created and index % 2 == 0:
                for category_code, years in (
                    (JobAgeRelaxation.Category.OBC, 3),
                    (JobAgeRelaxation.Category.SC, 5),
                ):
                    _, relaxation_created = JobAgeRelaxation.objects.get_or_create(
                        job=job,
                        category=category_code,
                        defaults={"relaxation_years": years},
                    )
                    counts["age_relaxations"] += int(relaxation_created)

    def _seed_contacts(self, counts):
        for name, phone_number, email, subject, message in DEMO_CONTACTS:
            _, created = ContactSubmission.objects.get_or_create(
                name=name,
                email=email,
                subject=subject,
                defaults={
                    "phone_number": phone_number,
                    "message": message,
                    "is_read": False,
                },
            )
            counts["contacts"] += int(created)

    def _seed_comments(self, author, counts):
        for body, status in DEMO_COMMENTS:
            _, created = Comment.objects.get_or_create(
                author=author,
                body=body,
                defaults={"status": status},
            )
            counts["comments"] += int(created)
