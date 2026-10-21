from django.db import migrations


BUILTIN_HOMEPAGE_SECTIONS = [
    (
        "results",
        "Latest Results",
        "Find result notices and candidate update information.",
        "award",
        10,
    ),
    (
        "admit-cards",
        "Admit Cards",
        "Keep exam-day documents and access instructions in one place.",
        "ticket",
        20,
    ),
    (
        "previous-papers",
        "Previous Year Papers",
        "Prepare with organized practice-paper resources.",
        "paper",
        30,
    ),
    (
        "answer-keys",
        "Answer Keys",
        "Review answer-key updates and objection-process guidance.",
        "file-search",
        40,
    ),
    (
        "syllabus",
        "Syllabus & Exam Pattern",
        "Plan preparation with structured syllabus references.",
        "book-open",
        50,
    ),
    (
        "updates",
        "Important Updates & Notifications",
        "See important notices once verified information is connected.",
        "bell",
        60,
    ),
]


def seed_public_sections(apps, schema_editor):
    """Make sure the built-in public sections exist (empty) and drop Jobs.

    Jobs is no longer a public feature, so any Jobs CMS entry is removed.
    The sections are created empty: real content is added through the CMS only.
    """
    ContentSection = apps.get_model("site_management", "ContentSection")
    ContentItem = apps.get_model("site_management", "ContentItem")

    for slug, title, description, icon, order in BUILTIN_HOMEPAGE_SECTIONS:
        ContentSection.objects.get_or_create(
            slug=slug,
            defaults={
                "area": "homepage",
                "title": title,
                "description": description,
                "icon": icon,
                "sort_order": order,
                "is_active": True,
            },
        )

    ContentSection.objects.filter(area="homepage", slug="jobs").delete()

    for section in ContentSection.objects.filter(area="navigation"):
        ContentItem.objects.filter(section=section, label__iexact="jobs").delete()

    for section in ContentSection.objects.filter(area="footer"):
        ContentItem.objects.filter(
            section=section,
            label__in=["Latest Jobs", "Check Eligibility"],
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("site_management", "0023_exam_exampdf"),
    ]

    operations = [
        migrations.RunPython(seed_public_sections, migrations.RunPython.noop),
    ]
