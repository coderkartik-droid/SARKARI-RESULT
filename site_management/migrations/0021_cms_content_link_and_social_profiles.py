from django.db import migrations, models

import site_management.models


class Migration(migrations.Migration):

    dependencies = [
        ("site_management", "0020_contactsubmission_phone_number"),
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
                    ("tools", "Tools landing page"),
                    ("footer", "Footer"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="contentitem",
            name="title_color",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional HEX color for the display title.",
                max_length=7,
                validators=[site_management.models.HEX_COLOR_VALIDATOR],
            ),
        ),
        migrations.AddField(
            model_name="contentitem",
            name="title_background_color",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional HEX background behind the title.",
                max_length=7,
                validators=[site_management.models.HEX_COLOR_VALIDATOR],
            ),
        ),
        migrations.AddField(
            model_name="contentitem",
            name="subtitle_color",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional HEX color for the subtitle text.",
                max_length=7,
                validators=[site_management.models.HEX_COLOR_VALIDATOR],
            ),
        ),
        migrations.AddField(
            model_name="contentitem",
            name="subtitle_background_color",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional HEX background behind the subtitle.",
                max_length=7,
                validators=[site_management.models.HEX_COLOR_VALIDATOR],
            ),
        ),
        migrations.CreateModel(
            name="ContentLink",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("label", models.CharField(help_text="Visible text shown to visitors.", max_length=120)),
                (
                    "url",
                    models.CharField(
                        help_text="Local path or http/https URL.",
                        max_length=500,
                        validators=[site_management.models.validate_public_url],
                    ),
                ),
                ("description", models.CharField(blank=True, max_length=250)),
                ("icon", models.CharField(blank=True, default="", help_text="Optional built-in icon identifier.", max_length=30)),
                (
                    "icon_url",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Optional custom icon URL.",
                        max_length=500,
                        validators=[site_management.models.validate_public_url],
                    ),
                ),
                (
                    "icon_color",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Optional icon color in HEX format.",
                        max_length=7,
                        validators=[site_management.models.HEX_COLOR_VALIDATOR],
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("open_new_tab", models.BooleanField(default=False)),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "content_item",
                    models.ForeignKey(
                        help_text="Content block this link belongs to.",
                        on_delete=models.deletion.CASCADE,
                        related_name="links",
                        to="site_management.contentitem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Content link",
                "verbose_name_plural": "Content links",
                "ordering": ["display_order", "pk"],
            },
        ),
        migrations.CreateModel(
            name="SocialMediaProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "platform",
                    models.CharField(
                        choices=[
                            ("telegram", "Telegram"),
                            ("instagram", "Instagram"),
                            ("facebook", "Facebook"),
                            ("whatsapp", "WhatsApp"),
                        ],
                        max_length=20,
                        unique=True,
                    ),
                ),
                (
                    "profile_url",
                    models.CharField(
                        help_text="Public profile or channel URL.",
                        max_length=500,
                        validators=[site_management.models.validate_public_url],
                    ),
                ),
                (
                    "custom_icon_url",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Optional custom icon image URL.",
                        max_length=500,
                        validators=[site_management.models.validate_public_url],
                    ),
                ),
                ("built_in_icon", models.CharField(blank=True, default="", help_text="Built-in icon identifier for the platform.", max_length=30)),
                (
                    "icon_color",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Optional HEX color for the platform icon.",
                        max_length=7,
                        validators=[site_management.models.HEX_COLOR_VALIDATOR],
                    ),
                ),
                ("accessible_label", models.CharField(blank=True, default="", max_length=80)),
                (
                    "display_location",
                    models.CharField(
                        choices=[
                            ("header", "Header"),
                            ("footer", "Footer"),
                            ("both", "Header + Footer"),
                        ],
                        default="both",
                        max_length=10,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Social media profile",
                "verbose_name_plural": "Social media profiles",
                "ordering": ["display_order", "pk"],
            },
        ),
    ]
