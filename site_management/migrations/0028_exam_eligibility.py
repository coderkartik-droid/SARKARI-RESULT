# Add candidate DOB window + accepted qualifications to the Exam section.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('site_management', '0027_contentlink_exam_alter_contentlink_content_item'),
        ('jobs', '0003_qualification_job_dob_dates_and_qualifications'),
    ]

    operations = [
        migrations.AddField(
            model_name='exam',
            name='dob_start_date',
            field=models.DateField(blank=True, help_text='Earliest eligible candidate date of birth (inclusive). This is a candidate DOB boundary, not the application opening date.', null=True),
        ),
        migrations.AddField(
            model_name='exam',
            name='dob_end_date',
            field=models.DateField(blank=True, help_text='Latest eligible candidate date of birth (inclusive). This is a candidate DOB boundary, not the application closing date.', null=True),
        ),
        migrations.AddField(
            model_name='exam',
            name='eligible_qualifications',
            field=models.ManyToManyField(blank=True, help_text='One or more qualifications accepted for this exam. A candidate qualifies if their qualification matches any selected option.', related_name='exams', to='jobs.qualification'),
        ),
    ]
