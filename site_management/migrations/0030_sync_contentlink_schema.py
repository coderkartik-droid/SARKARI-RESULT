"""Bring the ``contentlink`` table back in sync with the ``ContentLink`` model.

Migrations ``0026``/``0027`` added three columns to ``contentlink`` that the
model never declared:

* ``exam_id`` — a foreign key to ``site_management_exam`` (``ON DELETE CASCADE``
  at the ORM level, but a plain ``REFERENCES`` constraint at the database level),
* ``link_type`` and ``image`` — extra presentation columns.

Because the model no longer exposes these fields, Django's delete collector is
unaware of ``contentlink.exam_id``. Deleting an ``Exam`` (for example through
the admin changelist "delete selected" action) therefore leaves those rows
dangling, and SQLite raises ``IntegrityError: FOREIGN KEY constraint failed``
when the deferred foreign-key check runs at COMMIT time.

This migration fixes the drift in two steps:

1. ``_remove_orphaned_exam_links`` removes the legacy ``ContentLink`` rows that
   only ever belonged to an exam (``content_item`` is NULL). The current UI,
   forms and the ``ContentLinkForm`` all require a content item, so these rows
   are unreachable and cannot exist under the model's ``NOT NULL`` constraint.
   The step is idempotent and only touches rows that are already invalid.
2. The remaining operations drop the stale columns and restore the model's
   ``content_item`` / ``url`` definitions.

After this migration the database schema matches ``site_management/models.py``
exactly, so ``makemigrations --check`` succeeds and admin deletions no longer
trip the foreign-key constraint.
"""

from django.db import migrations, models
import django.db.models.deletion

import site_management.models


def _remove_orphaned_exam_links(apps, schema_editor):
    """Delete legacy exam-only links that the model can no longer represent.

    ``content_item`` is nullable in the pre-migration schema (added by migration
    ``0027``); rows with a NULL value have no owning content block and are not
    reachable from any view or form, so they cannot survive the ``NOT NULL``
    constraint applied below. Rows that already point at a content block are
    left completely untouched.
    """
    ContentLink = apps.get_model("site_management", "ContentLink")
    ContentLink.objects.filter(content_item__isnull=True).delete()


def _noop_reverse(apps, schema_editor):
    """Nothing to restore: the deleted rows were unreachable legacy data."""


class Migration(migrations.Migration):

    dependencies = [
        ("site_management", "0029_exam_resources"),
    ]

    operations = [
        migrations.RunPython(_remove_orphaned_exam_links, _noop_reverse),
        migrations.RemoveField(
            model_name="contentlink",
            name="exam",
        ),
        migrations.RemoveField(
            model_name="contentlink",
            name="image",
        ),
        migrations.RemoveField(
            model_name="contentlink",
            name="link_type",
        ),
        migrations.AlterField(
            model_name="contentlink",
            name="content_item",
            field=models.ForeignKey(
                help_text="Content block this link belongs to.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="links",
                to="site_management.contentitem",
            ),
        ),
        migrations.AlterField(
            model_name="contentlink",
            name="url",
            field=models.CharField(
                help_text="Local path or http/https URL.",
                max_length=500,
                validators=[site_management.models.validate_public_url],
            ),
        ),
    ]
