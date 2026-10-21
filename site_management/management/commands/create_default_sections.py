from django.core.management.base import BaseCommand
from site_management.models import ContentSection
from django.db import transaction


class Command(BaseCommand):
    help = 'Create default content sections for homepage'

    def handle(self, *args, **options):
        sections_data = [
            ('homepage', 'results', 'Results', 'Exam results and recruitment announcements', 'award', 1),
            ('homepage', 'admit-cards', 'Admit Cards', 'Exam admit cards and download links', 'ticket', 2),
            ('homepage', 'previous-papers', 'Previous Year Papers', 'Previous year question papers and answer keys', 'book-open', 3),
            ('homepage', 'answer-keys', 'Answer Keys', 'Official answer keys for exams', 'file-search', 4),
            ('homepage', 'jobs', 'Jobs', 'Government job notifications and recruitment updates', 'briefcase', 5),
        ]

        with transaction.atomic():
            for area, slug, title, description, icon, sort_order in sections_data:
                section, created = ContentSection.objects.get_or_create(
                    slug=slug,
                    defaults={
                        'area': area,
                        'title': title,
                        'description': description,
                        'icon': icon,
                        'sort_order': sort_order,
                        'is_active': True,
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'Created section: {title}'))
                else:
                    self.stdout.write(self.style.WARNING(f'Section already exists: {title}'))

        self.stdout.write(self.style.SUCCESS('Default sections created successfully'))
