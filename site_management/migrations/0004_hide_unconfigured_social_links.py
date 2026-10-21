from django.db import migrations


def hide_unconfigured_social_links(apps, schema_editor):
    ContentSection = apps.get_model("site_management", "ContentSection")
    social_section = ContentSection.objects.filter(slug="footer-social").first()
    if social_section and not social_section.items.filter(url__gt="").exists():
        social_section.is_active = False
        social_section.save(update_fields=["is_active"])
        social_section.items.filter(url="").update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("site_management", "0003_contentsection_special_areas"),
    ]

    operations = [
        migrations.RunPython(
            hide_unconfigured_social_links,
            migrations.RunPython.noop,
        ),
    ]
