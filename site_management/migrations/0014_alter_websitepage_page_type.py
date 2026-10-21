from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("site_management", "0013_fix_website_page_data"),
    ]

    operations = [
        migrations.AlterField(
            model_name="websitepage",
            name="page_type",
            field=models.CharField(
                choices=[
                    ("about_us", "About Us"),
                    ("contact_us", "Contact Us"),
                    ("privacy_policy", "Privacy Policy"),
                    ("content_details", "Content Details"),
                ],
                help_text="Type of page (About Us, Contact Us, Privacy Policy, or Content Details).",
                max_length=20,
                unique=True,
            ),
        ),
    ]
