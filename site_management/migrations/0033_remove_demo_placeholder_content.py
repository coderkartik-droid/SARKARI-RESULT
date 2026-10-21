"""Remove seeded demo/placeholder content from the public data display.

Two sources of "fake" public content are cleaned up here without deleting any
row:

1. ``WebsiteSettings`` was created by ``0002_seed_default_content`` using
   demo-flavoured model defaults (e.g. ``hero_note_title="Demo content"`` and a
   footer that advertised "illustrative sample listings"). These values are
   only cleared when they still match the original demo text, so any real copy
   an admin has already saved is left untouched.
2. ``0002_seed_default_content`` also seeded placeholder ``ContentItem`` rows
   whose labels begin with ``"Sample "`` into the homepage CMS sections. Those
   rows are deactivated (``is_active=False``) rather than deleted so they stop
   appearing publicly but remain available in the admin panel.

The accompanying ``AlterField`` operations make the affected ``WebsiteSettings``
fields optional and default to empty, so the public site never ships
placeholder text on a fresh install and admins can clear these fields.
"""

from django.db import migrations, models


# The exact placeholder strings written by ``0002_seed_default_content`` via the
# original model defaults. Used to decide whether a stored value is still the
# untouched demo text before clearing it.
DEMO_SETTING_VALUES = {
    "hero_note_title": "Demo content",
    "hero_note_body": (
        "Listings on this preview are illustrative only, not verified live notices."
    ),
    "hero_note_footer": (
        "Official updates will appear here when verified data is connected."
    ),
    "footer_description": (
        "A clear starting point for recruitment information and exam resources. "
        "This preview currently contains illustrative sample listings only."
    ),
    "footer_disclaimer": "Sample listings are not official notifications.",
}

# Prefix used by the placeholder items seeded into the homepage CMS sections.
DEMO_ITEM_LABEL_PREFIX = "Sample "


def remove_demo_placeholder_content(apps, schema_editor):
    WebsiteSettings = apps.get_model("site_management", "WebsiteSettings")
    ContentItem = apps.get_model("site_management", "ContentItem")

    settings = WebsiteSettings.objects.filter(pk=1).first()
    if settings is not None:
        updates = {
            field_name: ""
            for field_name, demo_value in DEMO_SETTING_VALUES.items()
            if getattr(settings, field_name) == demo_value
        }
        if updates:
            WebsiteSettings.objects.filter(pk=1).update(**updates)

    ContentItem.objects.filter(
        section__area="homepage",
        parent__isnull=True,
        label__startswith=DEMO_ITEM_LABEL_PREFIX,
    ).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("site_management", "0032_resourceurl"),
    ]

    operations = [
        migrations.AlterField(
            model_name="websitesettings",
            name="hero_note_title",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AlterField(
            model_name="websitesettings",
            name="hero_note_body",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="websitesettings",
            name="hero_note_footer",
            field=models.CharField(blank=True, default="", max_length=240),
        ),
        migrations.AlterField(
            model_name="websitesettings",
            name="footer_description",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="websitesettings",
            name="footer_disclaimer",
            field=models.CharField(blank=True, default="", max_length=240),
        ),
        migrations.RunPython(
            remove_demo_placeholder_content,
            migrations.RunPython.noop,
        ),
    ]
