"""
Seed general informational job entries for the Job model.

This command adds template entries demonstrating different job categories
and eligibility patterns. These are informational examples, not specific
recruitment notifications.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from jobs.models import Job, JobAgeRelaxation


class Command(BaseCommand):
    help = "Seed informational job entries for the Job model"

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm that content should be added to the database",
        )

    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError(
                "No content was added. Re-run with --confirm to proceed."
            )

        counts = {
            "jobs": 0,
            "age_relaxations": 0,
        }

        with transaction.atomic():
            self._seed_informational_jobs(counts)

        self.stdout.write(self.style.SUCCESS("Job informational content seeding completed."))
        for name, count in counts.items():
            self.stdout.write(f"  {name.replace('_', ' ').title()}: {count} added")

    def _seed_informational_jobs(self, counts):
        """Create informational job entries demonstrating various categories."""

        today = timezone.localdate()

        # Informational job 1: General administrative job template
        job1, created = Job.objects.get_or_create(
            title="INFORMATIONAL: Administrative Officer - General Eligibility Template",
            defaults={
                "organization": "Template Government Department",
                "qualification": "Graduate in any discipline from a recognized university",
                "min_qualification": "graduate",
                "location": "All India",
                "category": "Central",
                "vacancies_count": None,  # Not specified as this is a template
                "min_age": 21,
                "max_age": 30,
                "age_cutoff_date": today + timedelta(days=90),
                "application_start_date": today - timedelta(days=30),
                "application_end_date": today + timedelta(days=30),
                "official_notification_url": "#",
                "application_url": "#",
                "source_url": "#",
                "last_verified_date": None,
                "status": "published",
                "is_verified": False,  # Marked as not verified since it's a template
                "is_expired": False,
            },
        )
        counts["jobs"] += int(created)

        if created:
            # Add age relaxations as example
            for category_code, years in [
                (JobAgeRelaxation.Category.OBC, 3),
                (JobAgeRelaxation.Category.SC, 5),
                (JobAgeRelaxation.Category.ST, 5),
            ]:
                JobAgeRelaxation.objects.create(
                    job=job1,
                    category=category_code,
                    relaxation_years=years,
                )
                counts["age_relaxations"] += 1

        # Informational job 2: Clerical position template
        job2, created = Job.objects.get_or_create(
            title="INFORMATIONAL: Clerical Assistant - General Eligibility Template",
            defaults={
                "organization": "Template Recruitment Board",
                "qualification": "12th Pass or equivalent from a recognized board",
                "min_qualification": "12th",
                "location": "All India",
                "category": "Central",
                "vacancies_count": None,
                "min_age": 18,
                "max_age": 27,
                "age_cutoff_date": today + timedelta(days=60),
                "application_start_date": today - timedelta(days=20),
                "application_end_date": today + timedelta(days=20),
                "official_notification_url": "#",
                "application_url": "#",
                "source_url": "#",
                "last_verified_date": None,
                "status": "published",
                "is_verified": False,
                "is_expired": False,
            },
        )
        counts["jobs"] += int(created)

        if created:
            for category_code, years in [
                (JobAgeRelaxation.Category.OBC, 3),
                (JobAgeRelaxation.Category.SC, 5),
                (JobAgeRelaxation.Category.ST, 5),
            ]:
                JobAgeRelaxation.objects.create(
                    job=job2,
                    category=category_code,
                    relaxation_years=years,
                )
                counts["age_relaxations"] += 1

        # Informational job 3: Technical position template
        job3, created = Job.objects.get_or_create(
            title="INFORMATIONAL: Technical Engineer - General Eligibility Template",
            defaults={
                "organization": "Template Technical Recruitment Authority",
                "qualification": "B.Tech/B.E. in relevant engineering discipline from a recognized institution",
                "min_qualification": "btech",
                "location": "All India",
                "category": "Central",
                "vacancies_count": None,
                "min_age": 21,
                "max_age": 30,
                "age_cutoff_date": today + timedelta(days=75),
                "application_start_date": today - timedelta(days=25),
                "application_end_date": today + timedelta(days=25),
                "official_notification_url": "#",
                "application_url": "#",
                "source_url": "#",
                "last_verified_date": None,
                "status": "published",
                "is_verified": False,
                "is_expired": False,
            },
        )
        counts["jobs"] += int(created)

        if created:
            for category_code, years in [
                (JobAgeRelaxation.Category.OBC, 3),
                (JobAgeRelaxation.Category.SC, 5),
                (JobAgeRelaxation.Category.ST, 5),
            ]:
                JobAgeRelaxation.objects.create(
                    job=job3,
                    category=category_code,
                    relaxation_years=years,
                )
                counts["age_relaxations"] += 1

        # Informational job 4: State government template
        job4, created = Job.objects.get_or_create(
            title="INFORMATIONAL: State Administrative Service - General Eligibility Template",
            defaults={
                "organization": "Template State Public Service Commission",
                "qualification": "Graduate in any discipline from a recognized university",
                "min_qualification": "graduate",
                "location": "State-Wide",
                "category": "State",
                "vacancies_count": None,
                "min_age": 21,
                "max_age": 40,
                "age_cutoff_date": today + timedelta(days=100),
                "application_start_date": today - timedelta(days=35),
                "application_end_date": today + timedelta(days=35),
                "official_notification_url": "#",
                "application_url": "#",
                "source_url": "#",
                "last_verified_date": None,
                "status": "published",
                "is_verified": False,
                "is_expired": False,
            },
        )
        counts["jobs"] += int(created)

        if created:
            for category_code, years in [
                (JobAgeRelaxation.Category.OBC, 3),
                (JobAgeRelaxation.Category.SC, 5),
                (JobAgeRelaxation.Category.ST, 5),
            ]:
                JobAgeRelaxation.objects.create(
                    job=job4,
                    category=category_code,
                    relaxation_years=years,
                )
                counts["age_relaxations"] += 1

        # Informational job 5: Banking position template
        job5, created = Job.objects.get_or_create(
            title="INFORMATIONAL: Banking Probationary Officer - General Eligibility Template",
            defaults={
                "organization": "Template Banking Recruitment Board",
                "qualification": "Graduate in any discipline from a recognized university",
                "min_qualification": "graduate",
                "location": "All India",
                "category": "Banking",
                "vacancies_count": None,
                "min_age": 20,
                "max_age": 30,
                "age_cutoff_date": today + timedelta(days=80),
                "application_start_date": today - timedelta(days=28),
                "application_end_date": today + timedelta(days=28),
                "official_notification_url": "#",
                "application_url": "#",
                "source_url": "#",
                "last_verified_date": None,
                "status": "published",
                "is_verified": False,
                "is_expired": False,
            },
        )
        counts["jobs"] += int(created)

        if created:
            for category_code, years in [
                (JobAgeRelaxation.Category.OBC, 3),
                (JobAgeRelaxation.Category.SC, 5),
                (JobAgeRelaxation.Category.ST, 5),
                (JobAgeRelaxation.Category.PWD, 10),
            ]:
                JobAgeRelaxation.objects.create(
                    job=job5,
                    category=category_code,
                    relaxation_years=years,
                )
                counts["age_relaxations"] += 1
