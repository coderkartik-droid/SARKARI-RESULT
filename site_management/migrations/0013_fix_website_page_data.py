from django.db import migrations


def ensure_contact_page(apps, schema_editor):
    WebsitePage = apps.get_model("site_management", "WebsitePage")
    WebsitePage.objects.update_or_create(
        page_type="contact_us",
        defaults={
            "title": "Contact Us",
            "subtitle": "",
            "description": (
                "We are glad to hear from visitors and applicants who have questions about the website, "
                "service availability, or content updates.\n\n"
                "For general inquiries, use the contact information listed in the website settings, or "
                "send a message through the official channels maintained by the site administrator.\n\n"
                "Please include a clear subject and relevant details so we can respond appropriately and "
                "help direct your inquiry to the correct contact or source."
            ),
            "image": "",
            "image_alt": "",
            "image_caption": "",
            "link_url": "",
            "link_text": "",
            "is_published": True,
        },
    )


def deduplicate_privacy_policy_footer_links(apps, schema_editor):
    ContentSection = apps.get_model("site_management", "ContentSection")
    ContentItem = apps.get_model("site_management", "ContentItem")

    footer_sections = ContentSection.objects.filter(area="footer")
    for section in footer_sections:
        items = list(
            ContentItem.objects.filter(section=section, label="Privacy Policy").order_by("pk")
        )
        if not items:
            continue

        preferred = next(
            (item for item in items if item.url == "/privacy-policy/"),
            next((item for item in items if item.url and item.url.startswith("/")), None),
        )
        if preferred is None:
            preferred = items[0]

        preferred.url = "/privacy-policy/"
        preferred.save(update_fields=["url"])

        for item in items:
            if item.pk != preferred.pk:
                item.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("site_management", "0012_remove_duplicate_privacy_link"),
    ]

    operations = [
        migrations.RunPython(ensure_contact_page, migrations.RunPython.noop),
        migrations.RunPython(deduplicate_privacy_policy_footer_links, migrations.RunPython.noop),
    ]
