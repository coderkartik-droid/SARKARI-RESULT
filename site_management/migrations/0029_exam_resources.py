import django.db.models.deletion
from django.db import migrations, models

import site_management.models


class Migration(migrations.Migration):

    dependencies = [
        ("site_management", "0028_exam_eligibility"),
    ]

    operations = [
        migrations.AddField(
            model_name="exam",
            name="exam_date",
            field=models.DateField(
                blank=True,
                help_text=(
                    "Date of the exam or its main event. Drives the Upcoming Exams "
                    "(today or later) and Recent Exams (before today) sections."
                ),
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="AnswerSheet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Optional description or instructions shown on the public page.",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("published", "Published")],
                        default="draft",
                        help_text="Only published items appear on the public website.",
                        max_length=20,
                    ),
                ),
                (
                    "published_date",
                    models.DateField(
                        blank=True,
                        help_text=(
                            "Date shown publicly. Leave empty to publish immediately, or set a "
                            "future date to keep the item hidden until then."
                        ),
                        null=True,
                    ),
                ),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "pdf_file",
                    models.FileField(
                        help_text=(
                            "Answer-sheet PDF (required). PDF only, maximum size configured "
                            "with CMS_MAX_PDF_SIZE (default 20 MB)."
                        ),
                        upload_to=site_management.models.SafePDFUploadTo("cms/answer_sheets/"),
                        validators=[site_management.models.validate_content_pdf],
                    ),
                ),
                (
                    "exam",
                    models.ForeignKey(
                        blank=True,
                        help_text="Optional exam this answer sheet belongs to.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="answer_sheets",
                        to="site_management.exam",
                    ),
                ),
            ],
            options={
                "verbose_name": "Answer sheet",
                "verbose_name_plural": "Answer sheets",
                "ordering": ["sort_order", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="RegistrationResource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Optional description or instructions shown on the public page.",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("published", "Published")],
                        default="draft",
                        help_text="Only published items appear on the public website.",
                        max_length=20,
                    ),
                ),
                (
                    "published_date",
                    models.DateField(
                        blank=True,
                        help_text=(
                            "Date shown publicly. Leave empty to publish immediately, or set a "
                            "future date to keep the item hidden until then."
                        ),
                        null=True,
                    ),
                ),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "pdf_file",
                    models.FileField(
                        blank=True,
                        help_text=(
                            "Optional registration/application form PDF. PDF only, maximum size "
                            "configured with CMS_MAX_PDF_SIZE (default 20 MB)."
                        ),
                        upload_to=site_management.models.SafePDFUploadTo("cms/registration_forms/"),
                        validators=[site_management.models.validate_content_pdf],
                    ),
                ),
                (
                    "official_url",
                    models.CharField(
                        blank=True,
                        help_text="Optional official application URL (http/https).",
                        max_length=500,
                        validators=[site_management.models.validate_public_url],
                    ),
                ),
                (
                    "closing_date",
                    models.DateField(
                        blank=True,
                        help_text="Optional last date to apply shown on the public page.",
                        null=True,
                    ),
                ),
                (
                    "exam",
                    models.ForeignKey(
                        blank=True,
                        help_text="Optional exam this registration resource belongs to.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="registration_resources",
                        to="site_management.exam",
                    ),
                ),
            ],
            options={
                "verbose_name": "Registration form",
                "verbose_name_plural": "Registration forms",
                "ordering": ["sort_order", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="PreviousPaper",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Optional description or instructions shown on the public page.",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("published", "Published")],
                        default="draft",
                        help_text="Only published items appear on the public website.",
                        max_length=20,
                    ),
                ),
                (
                    "published_date",
                    models.DateField(
                        blank=True,
                        help_text=(
                            "Date shown publicly. Leave empty to publish immediately, or set a "
                            "future date to keep the item hidden until then."
                        ),
                        null=True,
                    ),
                ),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "exam_year",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Year the paper was held, e.g. 2025.",
                        null=True,
                    ),
                ),
                (
                    "pdf_file",
                    models.FileField(
                        help_text=(
                            "Paper PDF (required). PDF only, maximum size configured with "
                            "CMS_MAX_PDF_SIZE (default 20 MB)."
                        ),
                        upload_to=site_management.models.SafePDFUploadTo("cms/previous_papers/"),
                        validators=[site_management.models.validate_content_pdf],
                    ),
                ),
                (
                    "exam",
                    models.ForeignKey(
                        blank=True,
                        help_text="Optional exam this paper belongs to.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="previous_papers",
                        to="site_management.exam",
                    ),
                ),
            ],
            options={
                "verbose_name": "Previous paper",
                "verbose_name_plural": "Previous papers",
                "ordering": ["sort_order", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Result",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Optional description or instructions shown on the public page.",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("published", "Published")],
                        default="draft",
                        help_text="Only published items appear on the public website.",
                        max_length=20,
                    ),
                ),
                (
                    "published_date",
                    models.DateField(
                        blank=True,
                        help_text=(
                            "Date shown publicly. Leave empty to publish immediately, or set a "
                            "future date to keep the item hidden until then."
                        ),
                        null=True,
                    ),
                ),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "official_url",
                    models.CharField(
                        blank=True,
                        help_text="Official result URL (http/https). Required unless a result PDF is uploaded.",
                        max_length=500,
                        validators=[site_management.models.validate_public_url],
                    ),
                ),
                (
                    "pdf_file",
                    models.FileField(
                        blank=True,
                        help_text=(
                            "Optional result PDF. PDF only, maximum size configured with "
                            "CMS_MAX_PDF_SIZE (default 20 MB)."
                        ),
                        upload_to=site_management.models.SafePDFUploadTo("cms/results/"),
                        validators=[site_management.models.validate_content_pdf],
                    ),
                ),
                (
                    "exam",
                    models.ForeignKey(
                        blank=True,
                        help_text="Optional exam this result belongs to.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="results",
                        to="site_management.exam",
                    ),
                ),
            ],
            options={
                "verbose_name": "Result",
                "verbose_name_plural": "Results",
                "ordering": ["sort_order", "-created_at"],
            },
        ),
    ]
