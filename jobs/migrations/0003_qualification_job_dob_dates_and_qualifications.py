# Generated for the dynamic exam eligibility feature.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0002_jobagerelaxation_job_age_cutoff_date_job_max_age_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Qualification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.SlugField(help_text="Stable identifier used by the eligibility engine (e.g. '12th', 'graduate').", max_length=30, unique=True)),
                ('name', models.CharField(help_text='Human-readable label shown in the admin and public pages.', max_length=100, unique=True)),
                ('rank', models.PositiveSmallIntegerField(default=0, help_text='Relative level used for display ordering. Higher means a higher qualification.')),
                ('is_active', models.BooleanField(default=True, help_text='Inactive qualifications stay on existing exams but are hidden from new selections.')),
            ],
            options={
                'verbose_name': 'Qualification',
                'verbose_name_plural': 'Qualifications',
                'ordering': ['rank', 'name'],
            },
        ),
        migrations.AddField(
            model_name='job',
            name='dob_start_date',
            field=models.DateField(blank=True, help_text='Earliest eligible candidate date of birth (inclusive). This is a candidate DOB boundary, not the application opening date.', null=True),
        ),
        migrations.AddField(
            model_name='job',
            name='dob_end_date',
            field=models.DateField(blank=True, help_text='Latest eligible candidate date of birth (inclusive). This is a candidate DOB boundary, not the application closing date.', null=True),
        ),
        migrations.AddField(
            model_name='job',
            name='eligible_qualifications',
            field=models.ManyToManyField(blank=True, help_text='One or more qualifications accepted for this exam. A candidate qualifies if their qualification matches any selected option.', related_name='jobs', to='jobs.qualification'),
        ),
    ]
