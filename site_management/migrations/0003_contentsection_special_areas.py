from django.db import migrations, models


def move_special_sections(apps, schema_editor):
    ContentSection = apps.get_model("site_management", "ContentSection")
    ContentSection.objects.filter(slug="announcements").update(area="announcements")
    ContentSection.objects.filter(slug="hero-actions").update(area="hero_actions")


class Migration(migrations.Migration):
    dependencies = [
        ("site_management", "0002_seed_default_content"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contentsection",
            name="area",
            field=models.CharField(
                choices=[
                    ("navigation", "Navigation"),
                    ("homepage", "Homepage"),
                    ("announcements", "Announcements"),
                    ("hero_actions", "Homepage buttons"),
                    ("footer", "Footer"),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(move_special_sections, migrations.RunPython.noop),
    ]
