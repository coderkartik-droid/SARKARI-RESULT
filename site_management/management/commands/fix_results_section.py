from django.core.management.base import BaseCommand
from site_management.models import ContentSection


class Command(BaseCommand):
    help = 'Fix Results section to be in homepage area'

    def handle(self, *args, **options):
        results = ContentSection.objects.filter(slug='results').first()
        if results:
            results.area = 'homepage'
            results.title = 'Results'
            results.description = 'Exam results and recruitment announcements'
            results.icon = 'award'
            results.sort_order = 1
            results.save()
            self.stdout.write(self.style.SUCCESS('Updated Results section'))
        else:
            self.stdout.write(self.style.WARNING('Results section not found'))
