from django.db import migrations


def remove_duplicate_footer_page_links(apps, schema_editor):
    ContentItem = apps.get_model("site_management", "ContentItem")

    canonical_map = {
        "About Us": "/about-us/",
        "Privacy Policy": "/privacy-policy/",
        "Content Details": "/content-details/",
    }

    for label, canonical_url in canonical_map.items():
        items = list(
            ContentItem.objects.filter(section__area="footer", label=label).order_by("pk")
        )
        if not items:
            continue

        preferred = next(
            (item for item in items if item.url == canonical_url),
            next((item for item in items if item.url and item.url.startswith("/")), None),
        )
        if preferred is None:
            preferred = items[0]

        preferred.url = canonical_url
        preferred.save(update_fields=["url"])

        for item in items:
            if item.pk != preferred.pk:
                item.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("site_management", "0014_alter_websitepage_page_type"),
    ]

    operations = [
        migrations.RunPython(remove_duplicate_footer_page_links, migrations.RunPython.noop),
    ]
