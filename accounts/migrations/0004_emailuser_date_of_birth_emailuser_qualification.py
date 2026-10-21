# Generated for the dynamic exam eligibility feature.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_emailuser_username_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailuser',
            name='date_of_birth',
            field=models.DateField(blank=True, help_text="Used to check exam eligibility against each exam's date-of-birth window.", null=True, verbose_name='date of birth'),
        ),
        migrations.AddField(
            model_name='emailuser',
            name='qualification',
            field=models.CharField(blank=True, choices=[('10th', '10th Pass / Matriculation'), ('12th', '12th Pass / Intermediate'), ('iti', 'ITI (Industrial Training)'), ('diploma', 'Diploma / Polytechnic'), ('graduate', "Graduate / Bachelor's Degree"), ('btech', 'B.Tech / B.E.'), ('postgraduate', "Postgraduate / Master's Degree")], default='', help_text='Highest completed qualification, used for exam eligibility matching.', max_length=30, verbose_name='highest qualification'),
        ),
    ]
