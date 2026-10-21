from django.core.management.base import BaseCommand
from site_management.models import ContentSection, ContentItem
from django.urls import reverse


class Command(BaseCommand):
    help = 'Check and initialize tools section with tool cards'

    def handle(self, *args, **options):
        tools_section = ContentSection.objects.filter(area='tools').first()
        if not tools_section:
            tools_section = ContentSection.objects.create(
                area='tools',
                slug='tools',
                title='Photo Tools',
                description='Simple photo utilities to help you prepare images for government job applications',
                icon='tools',
                sort_order=0,
                is_active=True,
            )
            self.stdout.write(self.style.SUCCESS('Created Tools section'))
        else:
            self.stdout.write(self.style.WARNING(f'Tools section exists: {tools_section.title}'))

        tool_paths = {
            reverse('tools_image_resizer'): 'Image Resizer',
            reverse('tools_jpg_to_pdf'): 'JPG to PDF Converter',
            reverse('tools_photo_name_date'): 'Photo Name & Date Maker',
            reverse('tools_photo_signature_joiner'): 'Photo Signature Joiner',
            reverse('tools_resume_cv_photo'): 'Resume/CV Photo Tool',
        }

        for url, name in tool_paths.items():
            existing = ContentItem.objects.filter(section=tools_section, url=url).first()
            if not existing:
                ContentItem.objects.create(
                    section=tools_section,
                    label=name,
                    body=f'Use this {name.lower()} to prepare images for applications.',
                    url=url,
                    icon='tools',
                    sort_order=0,
                    is_active=True,
                )
                self.stdout.write(self.style.SUCCESS(f'Created tool card: {name}'))
            else:
                self.stdout.write(self.style.WARNING(f'Tool card already exists: {name}'))

        self.stdout.write(self.style.SUCCESS('Tools section initialized successfully'))
