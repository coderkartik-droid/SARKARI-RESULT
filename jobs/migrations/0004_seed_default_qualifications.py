# Seed the default qualification rows used by the dynamic exam eligibility feature.
# Kept in sync with jobs.models.QUALIFICATION_DEFINITIONS.

from django.db import migrations


DEFAULT_QUALIFICATIONS = [
    ("10th", "10th Pass / Matriculation", 1),
    ("12th", "12th Pass / Intermediate", 2),
    ("iti", "ITI (Industrial Training)", 2),
    ("diploma", "Diploma / Polytechnic", 3),
    ("graduate", "Graduate / Bachelor's Degree", 4),
    ("btech", "B.Tech / B.E.", 4),
    ("postgraduate", "Postgraduate / Master's Degree", 5),
]


def seed_default_qualifications(apps, schema_editor):
    qualification_model = apps.get_model("jobs", "Qualification")
    database = schema_editor.connection.alias

    for code, name, rank in DEFAULT_QUALIFICATIONS:
        qualification_model.objects.using(database).update_or_create(
            code=code,
            defaults={"name": name, "rank": rank, "is_active": True},
        )


def remove_default_qualifications(apps, schema_editor):
    qualification_model = apps.get_model("jobs", "Qualification")
    database = schema_editor.connection.alias

    qualification_model.objects.using(database).filter(
        code__in=[code for code, _name, _rank in DEFAULT_QUALIFICATIONS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0003_qualification_job_dob_dates_and_qualifications'),
    ]

    operations = [
        migrations.RunPython(
            seed_default_qualifications,
            remove_default_qualifications,
        ),
    ]
