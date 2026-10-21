import site_management.models
from django.core.validators import RegexValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("site_management", "0015_remove_duplicate_footer_links"),
    ]

    operations = [
        migrations.AddField(
            model_name="websitepage",
            name="contact_address",
            field=models.TextField(blank=True, help_text="Optional postal address shown on the Contact Us page."),
        ),
        migrations.AddField(
            model_name="websitepage",
            name="contact_email",
            field=models.EmailField(blank=True, help_text="Public contact email for the Contact Us page. Leave blank to hide."),
        ),
        migrations.AddField(
            model_name="websitepage",
            name="contact_facebook_url",
            field=models.CharField(blank=True, help_text="Optional Facebook page URL. Leave blank to hide the icon.", max_length=500, validators=[site_management.models.validate_public_url]),
        ),
        migrations.AddField(
            model_name="websitepage",
            name="contact_hours",
            field=models.CharField(blank=True, help_text="Optional office hours, e.g. 'Mon–Fri, 10 AM – 5 PM IST'.", max_length=240),
        ),
        migrations.AddField(
            model_name="websitepage",
            name="contact_instagram_url",
            field=models.CharField(blank=True, help_text="Optional Instagram profile URL. Leave blank to hide the icon.", max_length=500, validators=[site_management.models.validate_public_url]),
        ),
        migrations.AddField(
            model_name="websitepage",
            name="contact_intro",
            field=models.TextField(blank=True, help_text="Optional introduction shown above the contact form."),
        ),
        migrations.AddField(
            model_name="websitepage",
            name="contact_phone",
            field=models.CharField(blank=True, help_text="Optional phone number shown on the Contact Us page.", max_length=40, validators=[RegexValidator(regex=r"\A[0-9+()\-\s]{3,}\Z", message="Enter a valid phone number.")]),
        ),
        migrations.AddField(
            model_name="websitepage",
            name="contact_whatsapp_url",
            field=models.CharField(blank=True, help_text="Optional WhatsApp link, e.g. https://wa.me/919XXXXXXXXX. Leave blank to hide the icon.", max_length=500, validators=[site_management.models.validate_public_url]),
        ),
    ]
