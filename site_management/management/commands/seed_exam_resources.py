"""
Seed exam-linked resource content with educational/demonstration material.

This command adds general educational content to exam-linked resource models
(LatestJob, Result, AnswerSheet, RegistrationResource, PreviousPaper, Exam).
Content focuses on guidance and templates, not specific official notifications.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from jobs.models import Qualification
from site_management.models import (
    AnswerSheet,
    Exam,
    ExamLink,
    LatestJob,
    PreviousPaper,
    RegistrationResource,
    Result,
    ResourceURL,
)


class Command(BaseCommand):
    help = "Seed educational content for exam-linked resource models"

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
            "exams": 0,
            "latest_jobs": 0,
            "results": 0,
            "answer_sheets": 0,
            "registration_resources": 0,
            "previous_papers": 0,
            "exam_links": 0,
            "resource_urls": 0,
        }

        with transaction.atomic():
            self._seed_qualifications_if_needed()
            self._seed_exam_templates(counts)
            self._seed_latest_job_templates(counts)
            self._seed_result_templates(counts)
            self._seed_answer_sheet_templates(counts)
            self._seed_registration_templates(counts)
            self._seed_previous_paper_templates(counts)

        self.stdout.write(self.style.SUCCESS("Exam resource content seeding completed."))
        for name, count in counts.items():
            self.stdout.write(f"  {name.replace('_', ' ').title()}: {count} added")

    def _seed_qualifications_if_needed(self):
        """Ensure standard qualifications exist."""
        for code, name, rank in [
            ("10th", "10th Pass / Matriculation", 1),
            ("12th", "12th Pass / Intermediate", 2),
            ("iti", "ITI (Industrial Training)", 2),
            ("diploma", "Diploma / Polytechnic", 3),
            ("graduate", "Graduate / Bachelor's Degree", 4),
            ("btech", "B.Tech / B.E.", 4),
            ("postgraduate", "Postgraduate / Master's Degree", 5),
        ]:
            Qualification.objects.get_or_create(
                code=code,
                defaults={"name": name, "rank": rank, "is_active": True},
            )

    def _seed_exam_templates(self, counts):
        """Create template exam records for structure demonstration."""

        today = timezone.localdate()

        # Template 1: Administrative Services Exam Pattern
        exam1, created = Exam.objects.get_or_create(
            title="Government Administrative Services - Exam Pattern Template",
            defaults={
                "description": """This is a template demonstrating the exam structure for administrative services examinations. Use this as a reference for understanding typical examination patterns.

Exam Structure:
- Preliminary Examination: Objective type, screening test
- Main Examination: Descriptive type, subject-specific papers
- Interview/Personality Test: Assessing overall suitability

Typical Subjects:
- General Studies (History, Geography, Polity, Economy, Science)
- Current Affairs and General Knowledge
- Reasoning and Aptitude
- Language Paper (Regional/English)
- Optional Subject (for Main Examination)

Preparation Timeline:
- 6-12 months for serious preparation
- Daily study: 6-8 hours recommended
- Regular practice with mock tests
- Current affairs: Daily newspaper reading

Note: This is a general template. Actual exam patterns vary by recruiting organization. Always refer to the official notification for accurate information.""",
                "status": Exam.Status.PUBLISHED,
                "exam_date": today + timedelta(days=90),
                "is_active": True,
                "sort_order": 1,
            },
        )
        counts["exams"] += int(created)

        if created:
            # Add qualifications
            quals = Qualification.objects.filter(code__in=["graduate", "postgraduate"])
            exam1.eligible_qualifications.set(quals)

            # Add sample links
            link1, _ = ExamLink.objects.get_or_create(
                exam=exam1,
                url="#",
                link_text="Official Website (Template)",
                icon_type=ExamLink.IconType.WEBSITE,
                defaults={"sort_order": 1, "is_active": True},
            )
            counts["exam_links"] += 1

        # Template 2: Banking Examination Pattern
        exam2, created = Exam.objects.get_or_create(
            title="Banking Probationary Officer - Exam Pattern Template",
            defaults={
                "description": """Template demonstrating the typical examination pattern for banking PO/MT recruitment.

Selection Process:
1. Preliminary Examination
- Duration: 60 minutes
- Total Marks: 100
- Sections: English, Quantitative Aptitude, Reasoning

2. Main Examination
- Duration: 3 hours
- Total Marks: 200
- Sections: Reasoning, English, Quantitative, General Awareness, Computer Knowledge

3. Interview
- Duration: 15-20 minutes
- Assessing communication, personality, and banking awareness

Preparation Focus:
- Quantitative: Practice calculations daily
- Reasoning: Solve puzzles and logical problems
- English: Build vocabulary and comprehension
- General Awareness: Current affairs and banking awareness
- Computer: Basic operations and MS Office

Time Management:
- Prelims: 20 minutes per section
- Mains: 36 minutes per section approximately
- Practice with timed mock tests

Note: This is a general pattern. Refer to official IBPS or bank notification for exact details.""",
                "status": Exam.Status.PUBLISHED,
                "exam_date": today + timedelta(days=60),
                "is_active": True,
                "sort_order": 2,
            },
        )
        counts["exams"] += int(created)

        if created:
            quals = Qualification.objects.filter(code="graduate")
            exam2.eligible_qualifications.set(quals)

            link1, _ = ExamLink.objects.get_or_create(
                exam=exam2,
                url="#",
                link_text="Banking Exam Portal (Template)",
                icon_type=ExamLink.IconType.WEBSITE,
                defaults={"sort_order": 1, "is_active": True},
            )
            counts["exam_links"] += 1

    def _seed_latest_job_templates(self, counts):
        """Create template latest job entries with general guidance."""

        today = timezone.localdate()

        job1, created = LatestJob.objects.get_or_create(
            title="Understanding Government Job Categories - Informational Guide",
            defaults={
                "description": """This informational guide explains different categories of government jobs and helps you understand which category might suit your qualifications and interests.

Government Job Categories:

1. Central Government Jobs
- Recruited by UPSC, SSC, IBPS, RRB, etc.
- Administrative, technical, and clerical positions
- All-India postings possible
- Good salary and benefits

2. State Government Jobs
- Recruited by State PSCs and state boards
- Often require regional language knowledge
- Posting within the state
- Opportunity to serve home state

3. Banking Jobs
- Public sector banks, cooperative banks
- Urban postings with good career growth
- Professional work environment
- Transfer across India possible

4. Railway Jobs
- Technical and non-technical positions
- Good salary and travel benefits
- Job security and pension
- Various departmental opportunities

5. Defense Jobs
- Army, Navy, Air Force
- Paramilitary forces
- Prestigious career with discipline
- Excellent benefits and respect

Choosing the Right Category:
- Match with your educational qualification
- Consider your interests and aptitude
- Think about work-life balance preferences
- Research career progression opportunities
- Understand posting and transfer policies

Action Steps:
- Identify your eligibility
- Research various categories
- Talk to people in different services
- Choose based on long-term career goals
- Start focused preparation

Remember: Each category has its own preparation strategy. Choose wisely and prepare systematically.""",
                "status": LatestJob.Status.PUBLISHED,
                "published_date": today,
                "official_url": "#",
                "is_active": True,
                "sort_order": 1,
            },
        )
        counts["latest_jobs"] += int(created)

        job2, created = LatestJob.objects.get_or_create(
            title="Government Job Application Process - Step-by-Step Guide",
            defaults={
                "description": """A comprehensive guide to the government job application process, from finding vacancies to final selection.

Step 1: Finding Vacancies
- Regularly check official recruitment websites
- Follow employment news
- Subscribe to job alert services
- Join relevant Telegram/WhatsApp groups
- Check state government job portals

Step 2: Eligibility Check
- Read the official notification carefully
- Verify age limit and relaxations
- Check educational qualification requirements
- Understand category certificate requirements
- Confirm physical standards (if applicable)

Step 3: Application Preparation
- Gather required documents
- Scan documents in specified format
- Prepare photograph and signature
- Arrange fee payment method
- Fill personal details accurately

Step 4: Online Application
- Register on the official portal
- Fill the application form carefully
- Upload documents as per specifications
- Pay application fee
- Submit before deadline

Step 5: Examination Preparation
- Download syllabus from official notification
- Create a study schedule
- Gather study materials
- Practice previous year papers
- Take mock tests regularly

Step 6: Taking the Examination
- Download admit card on time
- Reach exam center early
- Follow exam instructions carefully
- Manage time effectively
- Attempt all sections strategically

Step 7: Post-Examination Process
- Check results on official website
- Prepare for next stage (if qualified)
- Attend document verification
- Complete medical examination (if required)
- Join after final selection

Important Tips:
- Apply early to avoid last-minute rush
- Keep application number safe
- Check email/SMS for updates
- Prepare all documents in advance
- Stay positive and persistent

Remember: Each recruitment has its own process. Always follow the official notification instructions.""",
                "status": LatestJob.Status.PUBLISHED,
                "published_date": today,
                "official_url": "#",
                "is_active": True,
                "sort_order": 2,
            },
        )
        counts["latest_jobs"] += int(created)

    def _seed_result_templates(self, counts):
        """Create template result entries with guidance."""

        today = timezone.localdate()

        result1, created = Result.objects.get_or_create(
            title="How to Check Government Exam Results - General Guide",
            defaults={
                "description": """This guide explains the general process of checking government examination results and understanding scorecards.

Finding Your Result:
1. Official Websites
- Recruitment board's official website
- Result-specific portals (sometimes separate)
- Check the notification for result declaration website

2. Required Information
- Roll number or registration number
- Date of birth
- Sometimes admit card number
- CAPTCHA verification (common)

3. Steps to Check Result
- Visit the official result website
- Find the result link for your examination
- Enter required details
- Submit and view your result
- Download and print the scorecard

Understanding Your Scorecard:
- Marks obtained in each section
- Total marks and qualifying marks
- Qualification status (Qualified/Not Qualified)
- Cut-off marks (if applicable)
- Rank or merit position (if declared)

Types of Results:
1. Written Examination Result
- Subject-wise marks
- Total marks
- Qualification for next stage

2. Final Result
- Written marks + Interview marks
- Final merit list
- Selection status

3. Provisional Result
- Subject to verification
- May change after document verification

What to Do After Result:
- If Qualified: Prepare for next stage or document verification
- If Not Qualified: Analyze performance, consider re-attempt
- Keep scorecard safe for future reference
- Check for re-evaluation options (if any)

Important Notes:
- Results are usually available in PDF format
- Official websites may be slow on result day due to high traffic
- Keep patience and try again if server is busy
- Download result immediately as it may be removed later
- Check for any corrigendum or updates

Common Issues:
- Server down: Wait and try again
- Roll number not found: Verify you entered correctly
- Result not displayed: Check if result is actually declared
- Website error: Try different browser or device

Remember: Always verify results from official sources only.""",
                "status": Result.Status.PUBLISHED,
                "published_date": today,
                "official_url": "#",
                "is_active": True,
                "sort_order": 1,
            },
        )
        counts["results"] += int(created)

        if created:
            ResourceURL.objects.create(
                content_object=result1,
                url="#",
                label="Result Checking Guide (Template)",
                target=ResourceURL.Target.SAME_TAB,
                sort_order=1,
                is_active=True,
            )
            counts["resource_urls"] += 1

    def _seed_answer_sheet_templates(self, counts):
        """Create template answer sheet entries with guidance."""

        today = timezone.localdate()

        as1, created = AnswerSheet.objects.get_or_create(
            title="Understanding Answer Keys and Response Sheets - Informational Guide",
            defaults={
                "description": """This guide explains answer keys, response sheets, and the objection process for government examinations.

What is an Answer Key?
- Official document showing correct answers
- Released after the examination
- Helps candidates estimate their score
- Available on the official website

What is a Response Sheet?
- Copy of your attempted answers
- Shows question-wise responses
- Helps analyze performance
- Released along with or after answer key

Types of Answer Keys:
1. Provisional Answer Key
- Released first
- Candidates can raise objections
- Subject to corrections
- Final answer key released after objections

2. Final Answer Key
- After considering objections
- Used for result preparation
- No further objections accepted
- Binding for all candidates

How to Use Answer Key:
1. Download from official website
2. Compare with your responses
3. Calculate estimated score
4. Check for incorrect answers in key
5. Raise objections if genuine errors found

Objection Process:
- Objection window specified in notification
- Usually 3-7 days after provisional key release
- Fee per question objection (refundable if objection accepted)
- Must provide evidence/document supporting objection
- Submit through official portal only

Raising Objections:
- Identify questions with errors
- Gather supporting evidence (textbooks, official sources)
- Pay objection fee online
- Submit objection with explanation
- Save acknowledgment for reference

After Objection Window:
- Expert committee reviews objections
- Valid objections lead to key correction
- Fee refunded for accepted objections
- Final answer key published
- Results prepared based on final key

Tips:
- Check answer key immediately after release
- Don't wait until last day for objections
- Provide strong evidence for objections
- Keep copy of submitted objections
- Follow official channels only

Important Notes:
- Answer keys are question-wise
- Sometimes different sets have different keys
- Marking scheme varies by exam
- Negative marking considerations
- Official key is final for result preparation

Remember: Use answer keys for learning and improvement, not just score estimation.""",
                "status": AnswerSheet.Status.PUBLISHED,
                "published_date": today,
                "is_active": True,
                "sort_order": 1,
            },
        )
        counts["answer_sheets"] += int(created)

    def _seed_registration_templates(self, counts):
        """Create template registration resource entries with guidance."""

        today = timezone.localdate()

        reg1, created = RegistrationResource.objects.get_or_create(
            title="Government Job Application Form - Filling Guide",
            defaults={
                "description": """A comprehensive guide to filling government job application forms correctly and avoiding common mistakes.

Pre-Application Preparation:
1. Document Collection
- Educational certificates (10th, 12th, Degree)
- Category certificate (if applicable)
- Date of birth proof
- Photograph (recent, passport size)
- Signature (black ink on white paper)
- ID proof (Aadhaar, PAN)

2. Document Scanning
- Format: JPEG/PNG as specified
- Size: Within limits (usually 20-100 KB)
- Resolution: Clear and readable
- Name files as per instructions

3. Technical Setup
- Stable internet connection
- Computer or smartphone
- Valid email address
- Mobile number for OTP
- Payment method ready

Filling the Application Form:

Section 1: Personal Information
- Name: As per educational certificates
- Father's Name: As per records
- Date of Birth: Verify with certificate
- Gender: Select correctly
- Marital Status: As applicable

Section 2: Contact Details
- Address: Complete and accurate
- Email: Valid and regularly checked
- Mobile: Active and accessible
- Emergency contact: If required

Section 3: Educational Qualification
- Institution names: Complete and correct
- Board/University: As per certificate
- Year of Passing: Accurate
- Percentage/CGPA: As per marksheet
- Subjects: If required

Section 4: Category Details
- Category: Select based on valid certificate
- Sub-category: If applicable
- PwD status: With valid certificate
- Ex-serviceman: If applicable

Section 5: Exam Center Preference
- Choose convenient centers
- Order of preference matters
- Check center codes correctly
- Consider travel arrangements

Section 6: Declaration
- Read carefully before agreeing
- Ensure all information is correct
- Understand terms and conditions
- Submit only after verification

Common Mistakes to Avoid:
- Spelling errors in name
- Incorrect date of birth
- Wrong category selection
- Incomplete information
- Poor quality document uploads
- Last-minute submission

After Submission:
- Note application number
- Save confirmation page
- Download application form
- Pay fee if not done during submission
- Check email for confirmation

Important Tips:
- Fill form at least 2-3 days before deadline
- Double-check every field
- Use correct spellings always
- Upload clear documents
- Keep copies of everything

Remember: Incorrect information can lead to rejection at any stage, even after selection.""",
                "status": RegistrationResource.Status.PUBLISHED,
                "published_date": today,
                "official_url": "#",
                "is_active": True,
                "sort_order": 1,
            },
        )
        counts["registration_resources"] += int(created)

        if created:
            ResourceURL.objects.create(
                content_object=reg1,
                url="#",
                label="Application Form Guide (Template)",
                target=ResourceURL.Target.SAME_TAB,
                sort_order=1,
                is_active=True,
            )
            counts["resource_urls"] += 1

    def _seed_previous_paper_templates(self, counts):
        """Create template previous paper entries with guidance."""

        today = timezone.localdate()

        pp1, created = PreviousPaper.objects.get_or_create(
            title="Using Previous Year Question Papers Effectively - Guide",
            defaults={
                "description": """This guide explains how to effectively use previous year question papers for government exam preparation.

Why Previous Papers Are Important:
1. Understand Exam Pattern
- Question distribution across sections
- Marking scheme and weightage
- Types of questions asked
- Difficulty level assessment

2. Identify Important Topics
- Frequently asked concepts
- Repeated question patterns
- High-weightage areas
- Trend analysis over years

3. Practice and Assessment
- Time management practice
- Speed and accuracy improvement
- Self-evaluation
- Weakness identification

How to Use Previous Papers:

Phase 1: Initial Learning (2-3 months before exam)
- Solve papers without time limit initially
- Focus on understanding question types
- Learn from solutions
- Note important topics

Phase 2: Practice Phase (1-2 months before exam)
- Solve with time limit
- Simulate exam conditions
- Track accuracy and speed
- Identify weak areas

Phase 3: Final Phase (Last month)
- Daily practice with papers
- Build exam temperament
- Refine strategy
- Boost confidence

Solving Strategy:
1. Before Solving
- Revise relevant topics
- Keep formula sheets ready
- Ensure you have enough time
- Choose a quiet environment

2. During Solving
- Read questions carefully
- Don't spend too much time on one question
- Mark difficult questions for review
- Maintain speed

3. After Solving
- Check answers thoroughly
- Analyze mistakes
- Learn correct approach
- Note patterns

Analysis and Learning:
- Create topic-wise performance record
- Identify recurring question types
- Note speed improvement areas
- Learn time-saving techniques

Sources for Previous Papers:
- Official recruitment websites
- Published question paper booklets
- Reputed coaching institute materials
- Online educational platforms
- Government job preparation websites

Tips for Maximum Benefit:
- Start with recent papers (last 3-5 years)
- Move to older papers for extra practice
- Don't memorize, understand concepts
- Focus on learning from mistakes
- Maintain a question bank

Common Mistakes:
- Solving without understanding concepts
- Just checking answers, not learning
- Not analyzing mistakes
- Memorizing questions instead of concepts
- Not simulating exam conditions

Remember: Previous papers indicate trends, don't guarantee the same pattern. Stay prepared for variations.""",
                "status": PreviousPaper.Status.PUBLISHED,
                "published_date": today,
                "is_active": True,
                "sort_order": 1,
            },
        )
        counts["previous_papers"] += int(created)

        if created:
            ResourceURL.objects.create(
                content_object=pp1,
                url="#",
                label="Previous Papers Guide (Template)",
                target=ResourceURL.Target.SAME_TAB,
                sort_order=1,
                is_active=True,
            )
            counts["resource_urls"] += 1
