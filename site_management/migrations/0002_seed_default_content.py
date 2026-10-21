from django.db import migrations


def seed_default_content(apps, schema_editor):
    WebsiteSettings = apps.get_model("site_management", "WebsiteSettings")
    ContentSection = apps.get_model("site_management", "ContentSection")
    ContentItem = apps.get_model("site_management", "ContentItem")

    WebsiteSettings.objects.get_or_create(pk=1)

    navigation, _ = ContentSection.objects.get_or_create(
        slug="main-navigation",
        defaults={
            "area": "navigation",
            "title": "Primary navigation",
            "description": "Public header navigation and dropdown entries.",
            "sort_order": 0,
            "is_active": True,
        },
    )
    nav_entries = [
        ("Home", "/", 0),
        ("Jobs", "#jobs", 10),
        ("Results", "#results", 20),
        ("Admit Cards", "#admit-cards", 30),
        ("Answer Keys", "#answer-keys", 40),
        ("Syllabus", "#syllabus", 50),
        ("Contact", "#contact", 60),
    ]
    for label, url, order in nav_entries:
        ContentItem.objects.get_or_create(
            section=navigation,
            parent=None,
            label=label,
            defaults={"url": url, "sort_order": order, "is_active": True},
        )

    home_sections = [
        (
            "jobs",
            "Latest Government Jobs",
            "Browse recruitment updates and application guidance.",
            "briefcase",
            (
                ("Sample recruitment notice overview", "An illustrative listing structure for a verified recruitment notice."),
                ("Sample eligibility and application guide", "A placeholder for qualifications, process, and application details."),
            ),
        ),
        (
            "results",
            "Latest Results",
            "Find result notices and candidate update information.",
            "result",
            (
                ("Sample examination result update", "A demo entry showing where verified result information will appear."),
                ("Sample merit list and scorecard notice", "A placeholder for official merit-list and scorecard links."),
            ),
        ),
        (
            "admit-cards",
            "Admit Cards",
            "Keep exam-day documents and access instructions in one place.",
            "ticket",
            (
                ("Sample admit card release update", "A demo entry for verified hall-ticket availability information."),
                ("Sample exam city and instructions notice", "A placeholder for official examination-day guidance."),
            ),
        ),
        (
            "answer-keys",
            "Answer Keys",
            "Review answer-key updates and objection-process guidance.",
            "key",
            (
                ("Sample provisional answer key notice", "A demo entry for an official answer-key publication."),
                ("Sample response sheet and objection guide", "A placeholder for verified response-sheet instructions."),
            ),
        ),
        (
            "syllabus",
            "Syllabus & Exam Pattern",
            "Plan preparation with structured syllabus references.",
            "book",
            (
                ("Sample examination syllabus outline", "A placeholder for an official subject-wise syllabus."),
                ("Sample exam pattern and marking guide", "A demo structure for verified paper-pattern details."),
            ),
        ),
        (
            "previous-papers",
            "Previous Year Question Papers",
            "Prepare with organized practice-paper resources.",
            "paper",
            (
                ("Sample previous paper collection", "A placeholder for verified and permission-cleared papers."),
                ("Sample practice set and solutions", "A demo entry for future practice resources."),
            ),
        ),
        (
            "updates",
            "Important Updates & Notifications",
            "See important notices once verified information is connected.",
            "bell",
            (
                ("Sample candidate notice", "A demo entry for an important verified candidate update."),
                ("Sample recruitment information update", "A placeholder for a confirmed department announcement."),
            ),
        ),
    ]
    for order, (slug, title, description, icon, items) in enumerate(home_sections):
        section, _ = ContentSection.objects.get_or_create(
            slug=slug,
            defaults={
                "area": "homepage",
                "title": title,
                "description": description,
                "icon": icon,
                "sort_order": order * 10,
                "is_active": True,
            },
        )
        for item_order, (label, body) in enumerate(items):
            ContentItem.objects.get_or_create(
                section=section,
                parent=None,
                label=label,
                defaults={
                    "body": body,
                    "sort_order": item_order * 10,
                    "is_active": True,
                },
            )

    for slug, title, description, order in (
        (
            "announcements",
            "Announcements",
            "Homepage announcement strip items.",
            80,
        ),
        (
            "hero-actions",
            "Hero buttons",
            "Optional buttons shown below the homepage search.",
            90,
        ),
    ):
        ContentSection.objects.get_or_create(
            slug=slug,
            defaults={
                "area": "homepage",
                "title": title,
                "description": description,
                "sort_order": order,
                "is_active": True,
            },
        )

    footer_sections = [
        (
            "footer-quick-links",
            "Quick links",
            (
                ("Home", "/", ""),
                ("Latest Jobs", "#jobs", ""),
                ("Results", "#results", ""),
                ("Admit Cards", "#admit-cards", ""),
                ("Answer Keys", "#answer-keys", ""),
                ("Contact", "#contact", ""),
            ),
        ),
        (
            "footer-information",
            "Useful information",
            (
                ("About Us", "#about", ""),
                ("Privacy Policy", "", "The privacy policy page has not been configured."),
                ("Terms & Conditions", "", "The terms page have not been configured."),
            ),
        ),
        (
            "footer-social",
            "Follow along",
            (
                ("Instagram", "", ""),
                ("Facebook", "", ""),
                ("YouTube", "", ""),
            ),
        ),
    ]
    for section_order, (slug, title, links) in enumerate(footer_sections):
        section, _ = ContentSection.objects.get_or_create(
            slug=slug,
            defaults={
                "area": "footer",
                "title": title,
                "sort_order": section_order * 10,
                "is_active": True,
            },
        )
        for item_order, (label, url, body) in enumerate(links):
            ContentItem.objects.get_or_create(
                section=section,
                parent=None,
                label=label,
                defaults={
                    "url": url,
                    "body": body,
                    "sort_order": item_order * 10,
                    "is_active": True,
                    "open_new_tab": False,
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ("site_management", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_default_content, migrations.RunPython.noop),
    ]
