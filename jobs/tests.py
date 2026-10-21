from datetime import date, timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Job, JobAgeRelaxation
from .forms import EligibilityCheckForm
from .eligibility import (
    calculate_age,
    evaluate_job_eligibility,
    check_eligibility_for_candidate,
)


class JobModelTests(TestCase):
    def setUp(self):
        self.today = timezone.now().date()
        self.active_job = Job.objects.create(
            title="SSC Combined Graduate Level Exam 2026",
            organization="Staff Selection Commission",
            qualification="Graduate",
            location="All India",
            category="Central",
            vacancies_count=8500,
            application_start_date=self.today - timedelta(days=5),
            application_end_date=self.today + timedelta(days=20),
            official_notification_url="https://ssc.gov.in/notice_sample.pdf",
            application_url="https://ssc.gov.in/apply",
            source_url="https://ssc.gov.in",
            last_verified_date=self.today,
            status="published",
            is_verified=True,
            is_expired=False,
        )

        self.expired_job = Job.objects.create(
            title="RRB Group D Recruitment",
            organization="Railway Recruitment Board",
            qualification="10th Pass",
            location="All India",
            category="Railway",
            vacancies_count=10000,
            application_start_date=self.today - timedelta(days=30),
            application_end_date=self.today - timedelta(days=2),
            status="published",
            is_verified=True,
            is_expired=True,
        )

        self.draft_job = Job.objects.create(
            title="UPSC Prelims Notification",
            organization="UPSC",
            qualification="Graduate",
            status="draft",
        )

    def test_job_string_representation(self):
        self.assertIn("SSC Combined Graduate Level", str(self.active_job))
        self.assertIn("Staff Selection Commission", str(self.active_job))

    def test_is_active_property(self):
        self.assertTrue(self.active_job.is_active)
        self.assertFalse(self.expired_job.is_active)
        self.assertFalse(self.draft_job.is_active)

    def test_to_dict_serialization(self):
        data = self.active_job.to_dict()
        self.assertEqual(data["id"], self.active_job.id)
        self.assertEqual(data["title"], "SSC Combined Graduate Level Exam 2026")
        self.assertEqual(data["qualification"], "Graduate")
        self.assertTrue(data["is_verified"])
        self.assertTrue(data["is_active"])
        self.assertFalse(data["is_expired"])

    def test_public_detail_endpoint_hides_unpublished_jobs(self):
        unverified_job = Job.objects.create(
            title="Unverified published listing",
            organization="Example organization",
            qualification="Graduate",
            status="published",
        )
        for job in (self.draft_job, unverified_job):
            response = self.client.get(
                reverse("jobs:job_detail", args=[job.pk])
            )
            self.assertEqual(response.status_code, 404)

        response = self.client.get(
            reverse("jobs:job_detail", args=[self.active_job.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job"]["id"], self.active_job.pk)

    def test_expired_verified_published_job_remains_available_as_expired(self):
        response = self.client.get(
            reverse("jobs:job_detail", args=[self.expired_job.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["job"]["is_active"])

    def test_public_job_listing_filters_orders_and_paginates(self):
        jobs = [self.active_job]
        for number in range(22):
            jobs.append(
                Job.objects.create(
                    title=f"Public recruitment {number}",
                    organization="Public Commission",
                    qualification="Graduate",
                    location="All India",
                    application_end_date=self.today + timedelta(days=10),
                    status="published",
                    is_verified=True,
                    is_expired=False,
                )
            )
        base_time = timezone.now()
        for number, job in enumerate(jobs):
            Job.objects.filter(pk=job.pk).update(
                created_at=base_time + timedelta(seconds=number)
            )

        first_page = self.client.get(reverse("jobs:list"))
        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.context["page_obj"].paginator.count, 23)
        self.assertEqual(len(first_page.context["page_obj"].object_list), 20)
        self.assertEqual(first_page.context["page_obj"].object_list[0].pk, jobs[-1].pk)
        self.assertContains(
            first_page,
            (
                f'class="portal-listing-card portal-listing-card-page '
                f'portal-card-main portal-full-card-link" '
                f'href="{reverse("jobs:detail", args=[jobs[-1].pk])}"'
            ),
        )
        self.assertNotContains(first_page, self.expired_job.title)
        self.assertNotContains(first_page, self.draft_job.title)

        second_page = self.client.get(reverse("jobs:list"), {"page": 2})
        self.assertEqual(len(second_page.context["page_obj"].object_list), 3)
        self.assertEqual(second_page.context["page_obj"].object_list[0].pk, jobs[2].pk)

    def test_job_listing_search_empty_and_invalid_pages(self):
        match = self.client.get(reverse("jobs:list"), {"q": "SSC Combined"})
        self.assertEqual(match.context["page_obj"].paginator.count, 1)
        self.assertEqual(
            match.context["page_obj"].object_list[0].pk,
            self.active_job.pk,
        )

        empty = self.client.get(reverse("jobs:list"), {"q": "no matching vacancy"})
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.context["page_obj"].paginator.count, 0)
        self.assertContains(empty, "No active verified jobs match")

        invalid = self.client.get(reverse("jobs:list"), {"page": "invalid"})
        beyond = self.client.get(reverse("jobs:list"), {"page": "999"})
        self.assertEqual(invalid.context["page_obj"].number, 1)
        self.assertEqual(beyond.context["page_obj"].number, 1)

    def test_homepage_limits_jobs_to_two_newest_and_view_all_is_category_specific(self):
        jobs = [self.active_job]
        for number in range(3):
            jobs.append(
                Job.objects.create(
                    title=f"Homepage recruitment {number}",
                    organization="Homepage Commission",
                    qualification="Graduate",
                    location="All India",
                    application_end_date=self.today + timedelta(days=10),
                    status="published",
                    is_verified=True,
                    is_expired=False,
                )
            )
        base_time = timezone.now()
        for number, job in enumerate(jobs):
            Job.objects.filter(pk=job.pk).update(
                created_at=base_time + timedelta(seconds=number)
            )

        response = self.client.get(reverse("home"))
        jobs_section = next(
            section for section in response.context["sections"] if section["id"] == "jobs"
        )
        self.assertEqual(len(jobs_section["items"]), 2)
        self.assertEqual(
            [item["id"] for item in jobs_section["items"]],
            [jobs[-1].pk, jobs[-2].pk],
        )
        self.assertEqual(jobs_section["list_url"], reverse("jobs:list"))

    def test_job_html_detail_excludes_jobs_not_eligible_for_public_listing(self):
        for job in (self.draft_job, self.expired_job):
            response = self.client.get(reverse("jobs:detail", args=[job.pk]))
            self.assertEqual(response.status_code, 404)

        response = self.client.get(reverse("jobs:detail", args=[self.active_job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.active_job.title)
        self.assertContains(response, "Check Eligibility")
        self.assertContains(
            response,
            f'href="{reverse("jobs:eligibility_check")}"',
        )


class JobEligibilityModelAndRelaxationTests(TestCase):
    def test_job_eligibility_fields_and_methods(self):
        job = Job.objects.create(
            title="UPSC Civil Services 2026",
            organization="UPSC",
            qualification="Graduate",
            min_qualification="graduate",
            min_age=21,
            max_age=32,
            age_cutoff_date=date(2026, 8, 1),
            status="published",
            is_verified=True,
        )
        self.assertTrue(job.has_age_criteria)
        self.assertEqual(job.age_criteria_display, "21 to 32 years")
        cutoff, source = job.get_effective_cutoff_date()
        self.assertEqual(cutoff, date(2026, 8, 1))
        self.assertEqual(source, "official")

        # Relaxation model
        relaxation = JobAgeRelaxation.objects.create(
            job=job,
            category=JobAgeRelaxation.Category.OBC,
            relaxation_years=3,
        )
        self.assertIn("OBC", str(relaxation))
        self.assertEqual(relaxation.relaxation_years, 3)

    def test_missing_age_criteria_display(self):
        job = Job.objects.create(
            title="Unspecified Criteria Exam",
            organization="State Board",
            status="published",
        )
        self.assertFalse(job.has_age_criteria)
        self.assertEqual(job.age_criteria_display, "Not configured")


class EligibilityFormTests(TestCase):
    def test_dob_is_required(self):
        form = EligibilityCheckForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn("dob", form.errors)

    def test_future_dob_is_rejected(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        form = EligibilityCheckForm(data={"dob": tomorrow.isoformat()})
        self.assertFalse(form.is_valid())
        self.assertIn("Date of birth cannot be in the future.", form.errors["dob"])

    def test_unreasonably_old_dob_is_rejected(self):
        ancient = date(1890, 5, 1)
        form = EligibilityCheckForm(data={"dob": ancient.isoformat()})
        self.assertFalse(form.is_valid())
        self.assertIn("Please enter a valid date of birth", form.errors["dob"][0])

    def test_qualification_is_required(self):
        valid_dob = date(2000, 5, 15)
        form = EligibilityCheckForm(data={"dob": valid_dob.isoformat()})
        self.assertFalse(form.is_valid())
        self.assertIn("qualification", form.errors)

    def test_valid_dob_and_qualification_are_accepted(self):
        valid_dob = date(2000, 5, 15)
        form = EligibilityCheckForm(
            data={"dob": valid_dob.isoformat(), "qualification": "graduate"}
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["qualification"], "graduate")

    def test_qualification_options_come_from_database_records(self):
        # The dropdown is populated from the Qualification table, not a
        # hardcoded parallel list.
        form = EligibilityCheckForm()
        choices = dict(form.fields["qualification"].choices)
        self.assertIn("graduate", choices)
        self.assertEqual(choices["graduate"], "Graduate / Bachelor's Degree")


class EligibilityMatchingEngineTests(TestCase):
    def setUp(self):
        self.cutoff = date(2026, 8, 1)
        # Exam: min_age=18, max_age=27, qualification=Graduate
        self.ssc_cgl = Job.objects.create(
            title="SSC CGL 2026",
            organization="Staff Selection Commission",
            qualification="Graduate",
            min_qualification="graduate",
            min_age=18,
            max_age=27,
            age_cutoff_date=self.cutoff,
            status="published",
            is_verified=True,
            is_expired=False,
        )
        # Exam: min_age=18, max_age=25, qualification=10th Pass
        self.rrb_group_d = Job.objects.create(
            title="RRB Group D 2026",
            organization="Railway Recruitment Board",
            qualification="10th Pass",
            min_qualification="10th",
            min_age=18,
            max_age=25,
            age_cutoff_date=self.cutoff,
            status="published",
            is_verified=True,
            is_expired=False,
        )
        # Exam with missing age criteria
        self.unconfigured_exam = Job.objects.create(
            title="Notice without Age Limits",
            organization="Various Dept",
            qualification="Graduate",
            status="published",
            is_verified=True,
            is_expired=False,
        )

    def test_calculate_age_accuracy(self):
        # Born 2000-08-01 vs Cutoff 2026-08-01 -> Exactly 26
        self.assertEqual(calculate_age(date(2000, 8, 1), self.cutoff), 26)
        # Born 2000-08-02 vs Cutoff 2026-08-01 -> 25 (birthday tomorrow)
        self.assertEqual(calculate_age(date(2000, 8, 2), self.cutoff), 25)
        # Leap year: Born 2004-02-29 vs 2026-02-28 -> 21
        self.assertEqual(calculate_age(date(2004, 2, 29), date(2026, 2, 28)), 21)
        # Leap year: Born 2004-02-29 vs 2026-03-01 -> 22
        self.assertEqual(calculate_age(date(2004, 2, 29), date(2026, 3, 1)), 22)

    def test_exact_minimum_age_boundary(self):
        # SSC CGL min_age is 18. Cutoff is 2026-08-01.
        # Candidate born 2008-08-01 is exactly 18 -> MATCHES
        res_18 = evaluate_job_eligibility(self.ssc_cgl, date(2008, 8, 1), qualification="graduate")
        self.assertTrue(res_18.age_matches)
        self.assertTrue(res_18.is_match)
        self.assertEqual(res_18.calculated_age, 18)

        # Candidate born 2008-08-02 is 17 (one day too young) -> DOES NOT MATCH
        res_17 = evaluate_job_eligibility(self.ssc_cgl, date(2008, 8, 2), qualification="graduate")
        self.assertFalse(res_17.age_matches)
        self.assertFalse(res_17.is_match)
        self.assertEqual(res_17.calculated_age, 17)

    def test_exact_maximum_age_boundary(self):
        # SSC CGL max_age is 27. Cutoff is 2026-08-01.
        # Candidate born 1998-08-02 is 27 years (turns 28 tomorrow) -> MATCHES (within 27)
        res_27 = evaluate_job_eligibility(self.ssc_cgl, date(1998, 8, 2), qualification="graduate")
        self.assertTrue(res_27.age_matches)
        self.assertTrue(res_27.is_match)
        self.assertEqual(res_27.calculated_age, 27)

        # Candidate born 1998-08-01 turned 28 today (28 completed years) -> DOES NOT MATCH (over 27)
        res_28 = evaluate_job_eligibility(self.ssc_cgl, date(1998, 8, 1), qualification="graduate")
        self.assertFalse(res_28.age_matches)
        self.assertFalse(res_28.is_match)
        self.assertEqual(res_28.calculated_age, 28)

    def test_missing_criteria_is_handled_explicitly_not_treated_as_valid(self):
        # unconfigured_exam has no min_age or max_age
        res = evaluate_job_eligibility(self.unconfigured_exam, date(2000, 1, 1))
        self.assertFalse(res.age_matches)
        self.assertFalse(res.is_match)
        self.assertEqual(res.age_criteria_display, "Criteria not configured in records")

    def test_optional_qualification_and_qualification_filtering(self):
        # Candidate age 24 (born 2002-01-01) matches both SSC (18-27) and RRB (18-25)
        dob = date(2002, 1, 1)

        # 1. No qualification provided -> matches both on age alone
        matches_no_qual = check_eligibility_for_candidate(dob, qualification=None)
        self.assertEqual(len(matches_no_qual), 2)
        match_titles = [r.job.title for r in matches_no_qual]
        self.assertIn("SSC CGL 2026", match_titles)
        self.assertIn("RRB Group D 2026", match_titles)

        # 2. Candidate qualification is '10th'
        # Can match RRB Group D (requires 10th), but NOT SSC CGL (requires Graduate)
        matches_10th = check_eligibility_for_candidate(dob, qualification="10th")
        self.assertEqual(len(matches_10th), 1)
        self.assertEqual(matches_10th[0].job.title, "RRB Group D 2026")

        # 3. Candidate qualification is 'graduate'
        # Can match both SSC CGL and RRB Group D (Graduate qualifies for 10th-level posts)
        matches_grad = check_eligibility_for_candidate(dob, qualification="graduate")
        self.assertEqual(len(matches_grad), 2)

    def test_unreliable_qualification_criteria_handling(self):
        # Exam with custom/unstructured qualification string
        custom_job = Job.objects.create(
            title="Specialist Consultant Exam",
            organization="Govt Enterprise",
            qualification="Specialized Domain Certificate with 5 years experience",
            min_age=20,
            max_age=35,
            age_cutoff_date=self.cutoff,
            status="published",
            is_verified=True,
            is_expired=False,
        )
        dob = date(2000, 1, 1)
        res = evaluate_job_eligibility(custom_job, dob, qualification="graduate")
        self.assertTrue(res.is_match)
        self.assertIsNone(res.qualification_matches)
        self.assertIn("Criteria not configured", res.qualification_status)
        self.assertEqual(res.status_badge, "Age matches entered criteria")


class EligibilityViewAndHomepageTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.job = Job.objects.create(
            title="IBPS PO Recruitment 2026",
            organization="Institute of Banking Personnel Selection",
            qualification="Graduate",
            min_qualification="graduate",
            min_age=20,
            max_age=30,
            age_cutoff_date=self.today,
            status="published",
            is_verified=True,
            is_expired=False,
        )

    def test_homepage_has_visible_check_eligibility_option_near_top(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        # Check Eligibility button in header actions
        self.assertIn('href="/jobs/check-eligibility/"', html)
        self.assertIn("Check Eligibility", html)
        # Check Eligibility also accessible in navigation and shortcuts
        self.assertIn('class="portal-eligibility-header-btn"', html)

    def test_eligibility_checker_get_renders_form(self):
        response = self.client.get(reverse("jobs:eligibility_check"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check Exam Eligibility")
        self.assertContains(response, 'id="id_dob"')
        self.assertContains(response, 'id="id_qualification"')
        self.assertContains(response, "Check Eligibility")

    def test_eligibility_checker_rejects_future_dob_in_view(self):
        tomorrow = self.today + timedelta(days=1)
        response = self.client.get(
            reverse("jobs:eligibility_check"),
            {"dob": tomorrow.isoformat(), "qualification": "graduate"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Date of birth cannot be in the future.")

    def test_eligibility_checker_matching_results(self):
        # Candidate born 25 years ago -> matches IBPS PO (20 - 30)
        dob = self.today - timedelta(days=25 * 365 + 6)
        response = self.client.get(
            reverse("jobs:eligibility_check"),
            {"dob": dob.isoformat(), "qualification": "graduate"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "IBPS PO Recruitment 2026")
        self.assertContains(response, reverse("jobs:detail", args=[self.job.pk]))
        self.assertContains(response, "20 to 30 years")
        self.assertContains(response, "Graduate")
        self.assertContains(response, "Matches entered criteria")

    def test_eligibility_checker_empty_state_when_no_match(self):
        # Candidate born 50 years ago -> outside 20 - 30 age bracket
        dob = self.today - timedelta(days=50 * 365 + 12)
        response = self.client.get(
            reverse("jobs:eligibility_check"),
            {"dob": dob.isoformat(), "qualification": "graduate"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "No exams found matching your date of birth and qualification."
        )
        self.assertNotContains(response, "IBPS PO Recruitment 2026")

    def test_eligibility_checker_requires_both_fields(self):
        # Missing qualification -> validation message, no evaluation.
        response = self.client.get(
            reverse("jobs:eligibility_check"), {"dob": self.today.isoformat()}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please select your qualification.")
        self.assertContains(response, "Please correct the errors above")

    def test_submitted_values_are_used_instead_of_saved_profile(self):
        from accounts.models import EmailUser

        # A logged-in user whose saved profile does NOT match the search.
        user = EmailUser.objects.create_user(
            username="wronguser", email="wrong@example.com", password="pw-12345"
        )
        user.date_of_birth = self.today - timedelta(days=50 * 365 + 12)
        user.qualification = "10th"
        user.save()
        self.client.force_login(user)

        # The submitted values (matching the job) must drive the result.
        dob = self.today - timedelta(days=25 * 365 + 6)
        response = self.client.get(
            reverse("jobs:eligibility_check"),
            {"dob": dob.isoformat(), "qualification": "graduate"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "IBPS PO Recruitment 2026")

        # The saved profile must NOT have been overwritten by the search.
        user.refresh_from_db()
        self.assertEqual(user.qualification, "10th")
        self.assertNotEqual(user.date_of_birth, dob)
