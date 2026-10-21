from django.core.validators import RegexValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("site_management", "0019_alter_websitepage_page_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="contactsubmission",
            name="phone_number",
            field=models.CharField(
                default="",
                max_length=20,
                validators=[
                    RegexValidator(
                        message="Enter a valid phone number.",
                        regex=r"\A\+?[0-9][0-9\s().-]{5,19}\Z",
                    )
                ],
            ),
            preserve_default=False,
        ),
    ]
