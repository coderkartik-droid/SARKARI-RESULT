"""
Seed useful, time-insensitive content for the Sarkari Result website.

This command adds:
- Educational guidance for government job preparation
- General information about job categories
- Proper legal templates for static pages
- Study resources and preparation tips
- FAQ-style content

All content is general guidance and educational material, not specific
official announcements or time-sensitive notifications.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from site_management.models import (
    ContentItem,
    ContentLink,
    ContentSection,
    WebsitePage,
    WebsiteSettings,
)


class Command(BaseCommand):
    help = "Seed useful educational content for the Sarkari Result website"

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
            "pages": 0,
            "sections": 0,
            "content_items": 0,
            "content_links": 0,
        }

        with transaction.atomic():
            self._seed_website_pages(counts)
            self._seed_preparation_guides(counts)
            self._seed_job_category_info(counts)
            self._seed_study_resources(counts)
            self._seed_faq_content(counts)

        self.stdout.write(self.style.SUCCESS("Useful content seeding completed."))
        for name, count in counts.items():
            self.stdout.write(f"  {name.replace('_', ' ').title()}: {count} added")

    def _seed_website_pages(self, counts):
        """Create proper static page content with legal templates."""

        # About Us
        _, created = WebsitePage.objects.get_or_create(
            page_type=WebsitePage.PageType.ABOUT_US,
            defaults={
                "title": "About Sarkari Result",
                "subtitle": "Your Gateway to Government Job Information",
                "description": """Sarkari Result is a comprehensive information portal dedicated to helping candidates find government job opportunities, exam results, admit cards, and preparation resources across India.

Our Mission
We aim to provide clear, accurate, and timely information about government recruitment notifications, examination schedules, results, and related resources. Our goal is to simplify the job search process for candidates by consolidating information from various official sources in one accessible location.

What We Offer
- Government job notifications from central and state departments
- Examination schedules and admit card information
- Result announcements and scorecard details
- Preparation resources and study materials
- Eligibility guidance and application assistance

Information Accuracy
We strive to provide accurate information sourced from official government websites and recruitment boards. However, candidates are always advised to verify details directly with the issuing authority before taking any action based on information found on this website.

Disclaimer
This website is an information aggregator and does not represent any government department or recruitment board. All recruitment notifications, exam dates, results, and other official information are sourced from respective official portals. We do not guarantee the completeness or accuracy of any information and encourage users to cross-verify with official sources.

Contact Us
For queries, suggestions, or feedback, please use our contact form. We aim to respond to genuine inquiries within a reasonable time frame.""",
                "is_published": True,
            },
        )
        counts["pages"] += int(created)

        # Contact Us
        _, created = WebsitePage.objects.get_or_create(
            page_type=WebsitePage.PageType.CONTACT_US,
            defaults={
                "title": "Contact Us",
                "subtitle": "Get in Touch",
                "description": """Have a question or feedback? We'd love to hear from you.

Please use the contact form below to reach out. For specific recruitment-related queries, we recommend contacting the official recruitment board or department directly, as they can provide authoritative answers about notifications, eligibility, and application status.

What We Can Help With
- General questions about using this website
- Reporting errors or broken links
- Suggestions for improving the site
- Feedback on content presentation

Response Time
We aim to respond to genuine inquiries within 2-3 business days. Please note that we cannot provide information about specific recruitment processes, exam results, or application status—these must be obtained from the official authorities.

Important Note
This contact form is not a channel for communicating with government departments or recruitment boards. For official matters, always use the contact information provided in the official recruitment notification.""",
                "contact_intro": "Fill out the form below and we'll get back to you as soon as possible.",
                "contact_hours": "Monday - Friday: 10:00 AM - 6:00 PM IST",
                "is_published": True,
            },
        )
        counts["pages"] += int(created)

        # Privacy Policy
        _, created = WebsitePage.objects.get_or_create(
            page_type=WebsitePage.PageType.PRIVACY_POLICY,
            defaults={
                "title": "Privacy Policy",
                "subtitle": "Your Privacy Matters",
                "description": """Last Updated: October 2026

Introduction
This Privacy Policy explains how we collect, use, and protect your personal information when you use the Sarkari Result website. By using our website, you agree to the terms of this policy.

Information We Collect
1. Information You Provide
- Contact form submissions (name, email, phone number, message)
- User account information (if you register for an account)
- Any other information you voluntarily provide

2. Automatically Collected Information
- IP address and browser type
- Device information
- Pages visited and time spent on the site
- Referring website

How We Use Your Information
- To respond to your inquiries via the contact form
- To improve our website and user experience
- To send you updates if you have subscribed (with your consent)
- To analyze usage patterns and website performance

Data Security
We implement reasonable security measures to protect your personal information. However, no method of transmission over the internet is completely secure, and we cannot guarantee absolute security.

Third-Party Services
Our website may use third-party services such as analytics tools and content delivery networks. These services may collect information in accordance with their own privacy policies.

Cookies
We use cookies to enhance your browsing experience, analyze site traffic, and personalize content. You can control cookie settings through your browser.

Your Rights
You have the right to:
- Access your personal information
- Request correction of inaccurate information
- Request deletion of your personal information
- Opt out of marketing communications

Children's Privacy
Our website is not intended for children under 13. We do not knowingly collect personal information from children.

Changes to This Policy
We may update this privacy policy from time to time. We will notify users of significant changes by posting the new policy on this page.

Contact Us
For privacy-related questions, please use our contact form.""",
                "is_published": True,
            },
        )
        counts["pages"] += int(created)

        # Terms and Conditions
        _, created = WebsitePage.objects.get_or_create(
            page_type=WebsitePage.PageType.TERMS_AND_CONDITIONS,
            defaults={
                "title": "Terms and Conditions",
                "subtitle": "Terms of Use",
                "description": """Last Updated: October 2026

Acceptance of Terms
By accessing and using the Sarkari Result website, you accept and agree to be bound by these Terms and Conditions. If you do not agree to these terms, please do not use this website.

Purpose of the Website
This website is an information aggregator that provides details about government job notifications, exam results, admit cards, and related resources sourced from official government portals. We do not represent any government department or recruitment board.

Accuracy of Information
While we strive to provide accurate and up-to-date information, we make no warranties about the completeness, reliability, or accuracy of any information. All users are advised to verify information directly with official sources before taking any action.

Limitation of Liability
We shall not be liable for any loss or damage arising from the use of this website or reliance on any information provided herein. This includes, but is not limited to, direct, indirect, incidental, or consequential damages.

User Responsibilities
- Verify all information with official sources before applying
- Use the information provided for legitimate purposes only
- Do not attempt to circumvent any security measures
- Respect the intellectual property rights of content providers

Intellectual Property
All content on this website, including text, graphics, logos, and software, is the property of Sarkari Result or its content suppliers and is protected by copyright laws.

External Links
Our website may contain links to external websites, including official government portals. We are not responsible for the content or privacy practices of these external sites.

Modifications to Terms
We reserve the right to modify these terms at any time. Continued use of the website after changes constitutes acceptance of the modified terms.

Governing Law
These terms shall be governed by and construed in accordance with the laws of India. Any disputes shall be subject to the exclusive jurisdiction of the courts in India.

Contact
For questions about these terms, please use our contact form.""",
                "is_published": True,
            },
        )
        counts["pages"] += int(created)

        # Disclaimer
        _, created = WebsitePage.objects.get_or_create(
            page_type=WebsitePage.PageType.DISCLAIMER,
            defaults={
                "title": "Disclaimer",
                "subtitle": "Important Notice",
                "description": """General Disclaimer
Sarkari Result is an informational website that aggregates content from various official government sources. We are not affiliated with, endorsed by, or connected to any government department, recruitment board, or examination authority.

Information Accuracy
While we make every effort to provide accurate and timely information, we cannot guarantee the completeness, correctness, or currency of any information provided on this website. Users are strongly advised to:

- Verify all details with the official recruitment notification
- Check the official website of the recruiting organization
- Confirm exam dates, application deadlines, and eligibility criteria from official sources
- Rely only on official sources for making decisions about applications and career choices

No Recruitment Authority
This website does not conduct any recruitment examinations, process applications, or declare results. All recruitment processes are handled by the respective government departments and recruitment boards mentioned in the notifications.

Third-Party Links
This website contains links to external websites, including official government portals. We are not responsible for the content, availability, or practices of these external sites. The inclusion of any link does not imply endorsement.

No Legal Advice
Information provided on this website is for general informational purposes only and does not constitute legal, professional, or career advice. Users should consult appropriate professionals for specific advice.

Errors and Omissions
We reserve the right to correct errors or inaccuracies at any time without prior notice. We are not liable for any damages arising from errors or omissions in the content.

Updates
Government recruitment notifications, exam schedules, and results are subject to change by the issuing authorities. We strive to update our content promptly, but there may be delays between official announcements and updates on this website.

User Responsibility
By using this website, you acknowledge that:
- You have read and understood this disclaimer
- You will verify all information with official sources
- We are not liable for any decisions made based on information provided here
- Use of this website is at your own risk

Contact
For specific queries about recruitment or examinations, please contact the official authority directly using the contact information provided in their official notification.""",
                "is_published": True,
            },
        )
        counts["pages"] += int(created)

        # Content Details
        _, created = WebsitePage.objects.get_or_create(
            page_type=WebsitePage.PageType.CONTENT_DETAILS,
            defaults={
                "title": "Content Details",
                "subtitle": "About Our Content",
                "description": """Content Sources
Our content is primarily sourced from:
- Official government department websites
- Recruitment board notifications and press releases
- Examination authority announcements
- Public service commission websites
- University and institutional admission portals

Content Categories
We organize information into the following categories:

1. Government Jobs
- Central government recruitment notifications
- State government job openings
- Public sector undertakings (PSUs)
- Banking and financial sector jobs
- Railway and defense recruitment

2. Examination Information
- Exam schedules and dates
- Admit card release information
- Result announcements
- Answer key publications
- Syllabus and exam patterns

3. Admissions
- University admission notifications
- Entrance exam information
- Scholarship announcements
- Counseling schedules

4. Resources
- Previous year question papers
- Study materials and notes
- Preparation tips and strategies
- Eligibility guidance

Content Updates
We monitor official sources regularly and update our content as new information becomes available. However, there may be delays between official announcements and our updates. Always check official sources for the most current information.

User-Contributed Content
We do not accept user-submitted job notifications or recruitment information. All content is curated by our team from verified official sources.

Feedback and Corrections
If you find any errors or outdated information, please use our contact form to let us know. We appreciate your help in maintaining accurate content.""",
                "is_published": True,
            },
        )
        counts["pages"] += int(created)

    def _seed_preparation_guides(self, counts):
        """Create general preparation guidance content."""

        section, created = ContentSection.objects.get_or_create(
            slug="preparation-guides",
            defaults={
                "area": ContentSection.Area.HOMEPAGE,
                "title": "Preparation Guides",
                "description": "General guidance for government job preparation",
                "icon": "book",
                "sort_order": 10,
                "is_active": True,
            },
        )
        counts["sections"] += int(created)

        guides = [
            {
                "label": "How to Start Government Job Preparation",
                "body": """Starting your government job preparation journey requires a systematic approach. Here's a step-by-step guide:

1. Understand the Landscape
Government jobs in India are offered by various organizations:
- Central government departments (UPSC, SSC, IBPS, etc.)
- State public service commissions
- Railway recruitment boards
- Banking institutions
- Defense services
- PSUs and public sector organizations

2. Choose Your Target
Based on your qualification and interests:
- 10th/12th Pass: Clerk, constable, multitasking staff positions
- Graduate: Administrative services, banking PO, teaching positions
- Professional degrees: Specialist roles, engineering services, medical services

3. Know the Selection Process
Most government jobs follow this pattern:
- Written examination (preliminary and/or mains)
- Skill test or interview (depending on the post)
- Document verification
- Medical examination (for certain posts)

4. Create a Study Plan
- Allocate dedicated study hours daily
- Focus on syllabus coverage first
- Practice previous year papers
- Take mock tests regularly
- Revise consistently

5. Stay Updated
- Follow official websites regularly
- Read newspapers for current affairs
- Join reputable study groups or forums
- Set up notifications for important dates

6. Develop Required Skills
- General awareness and current affairs
- Quantitative aptitude
- Reasoning ability
- English/Hindi language skills
- Computer literacy (for most posts)

Remember: Consistency and discipline are key to success in government job examinations.""",
                "short_description": "A systematic approach to starting your government job preparation journey",
                "icon": "compass",
                "sort_order": 1,
            },
            {
                "label": "Common Selection Process Stages",
                "body": """Understanding the typical selection process helps you prepare effectively:

Stage 1: Written Examination
- Preliminary Exam: Screening test with objective questions
- Mains Exam: Detailed test with descriptive/objective questions
- Subjects vary by post (general awareness, reasoning, aptitude, domain knowledge)

Stage 2: Skill Test (if applicable)
- Typing test for clerical positions
- Stenography test for stenographer posts
- Computer proficiency test
- Physical efficiency test for defense/police roles

Stage 3: Interview/Personality Test
- Assessing communication skills
- Testing subject knowledge depth
- Evaluating problem-solving ability
- Understanding candidate's motivation

Stage 4: Document Verification
- Original educational certificates
- Proof of age (birth certificate/school certificate)
- Caste/category certificates (if applicable)
- Identity proof (Aadhaar, PAN card)
- Photographs and signatures

Stage 5: Medical Examination
- Basic health check-up
- Vision and hearing tests
- Specific medical standards for certain posts

Tips for Each Stage:
- Prepare thoroughly for written exams with syllabus-focused study
- Practice regularly for skill tests
- Stay calm and confident during interviews
- Keep all documents organized and ready
- Maintain good physical health

Each stage is eliminatory, so perform your best at every step.""",
                "short_description": "Learn about the typical stages in government job selection processes",
                "icon": "list-checks",
                "sort_order": 2,
            },
            {
                "label": "Time Management Strategies for Exams",
                "body": """Effective time management is crucial for success in competitive examinations:

Before the Exam
- Create a realistic study schedule
- Allocate time based on your strengths and weaknesses
- Include breaks to avoid burnout
- Set daily and weekly targets
- Track your progress regularly

During the Exam
- Read all questions carefully before attempting
- Start with questions you're confident about
- Don't spend too much time on difficult questions
- Mark difficult questions to revisit later
- Keep track of time remaining

Specific Strategies:
Quantitative Aptitude:
- Practice mental calculations
- Learn shortcuts and tricks
- Attempt easier questions first
- Don't get stuck on complex problems

Reasoning:
- Identify question patterns quickly
- Use diagrams for visual reasoning
- Practice different types regularly
- Stay calm under pressure

General Awareness:
- Read newspapers daily
- Focus on current affairs of last 6-12 months
- Make notes of important events
- Revise regularly

Language Section:
- Improve vocabulary through daily reading
- Practice grammar rules
- Attempt comprehension passages carefully
- Manage time for both reading and writing

Practice with Mock Tests:
- Simulate exam conditions
- Practice with time limits
- Analyze your performance after each test
- Identify and work on weak areas

Remember: Speed and accuracy both matter. Balance is key.""",
                "short_description": "Effective time management techniques for competitive examinations",
                "icon": "clock",
                "sort_order": 3,
            },
        ]

        for guide in guides:
            item, created = ContentItem.objects.get_or_create(
                section=section,
                label=guide["label"],
                defaults={
                    "body": guide["body"],
                    "short_description": guide["short_description"],
                    "icon": guide["icon"],
                    "sort_order": guide["sort_order"],
                    "is_active": True,
                    "show_on_homepage": True,
                },
            )
            counts["content_items"] += int(created)

    def _seed_job_category_info(self, counts):
        """Create informational content about government job categories."""

        section, created = ContentSection.objects.get_or_create(
            slug="job-categories",
            defaults={
                "area": ContentSection.Area.HOMEPAGE,
                "title": "Government Job Categories",
                "description": "Information about different types of government jobs",
                "icon": "briefcase",
                "sort_order": 20,
                "is_active": True,
            },
        )
        counts["sections"] += int(created)

        categories = [
            {
                "label": "Central Government Jobs",
                "body": """Central government jobs are offered by various ministries and departments under the Government of India. These positions are typically recruited through:

Major Recruitment Bodies:
- UPSC (Union Public Service Commission): Civil Services, Engineering Services, Combined Medical Services, etc.
- SSC (Staff Selection Commission): CGL, CHSL, CPO, GD Constable, and various other examinations
- IBPS (Institute of Banking Personnel Selection): PO, Clerk, Specialist Officer posts in public sector banks
- Railway Recruitment Boards (RRB): NTPC, Group D, Level 1 posts in Indian Railways
- Other specialized boards for defense, postal, and other services

Types of Positions:
- Group A: Administrative and managerial roles (IAS, IPS, IFS, etc.)
- Group B: Gazetted and non-gazetted officer positions
- Group C: Clerical and supervisory positions
- Group D: Multi-tasking staff and support roles

Eligibility:
- Varies by position (10th pass to postgraduate)
- Age limits typically range from 18-32 years
- Relaxations available for reserved categories
- Physical standards for certain posts (defense, police)

Benefits:
- Job security and stability
- Regular salary increments
- Pension and retirement benefits
- Medical facilities
- Housing allowances in many posts
- Work-life balance compared to private sector

Preparation Focus:
- General studies and current affairs
- Subject-specific knowledge
- Aptitude and reasoning
- English language skills
- Interview preparation for Group A and B posts""",
                "short_description": "Overview of central government job opportunities and recruitment processes",
                "icon": "building",
                "sort_order": 1,
            },
            {
                "label": "State Government Jobs",
                "body": """State government jobs are offered by various state departments and are recruited through State Public Service Commissions and other state-level recruitment boards.

Recruitment Bodies:
- State Public Service Commissions (e.g., UPPSC, BPSC, MPSC)
- State Subordinate Services Selection Boards
- State-level police recruitment boards
- State education recruitment boards
- Department-specific recruitment notifications

Types of Positions:
- State Administrative Services (equivalent to IAS at state level)
- State Police Services
- Revenue department positions
- Education department roles (teachers, lecturers)
- Health department positions
- Engineering and technical roles in state departments
- Clerical and support staff

Eligibility Criteria:
- Often require knowledge of regional language
- Domicile/residency requirements for some posts
- Age limits vary by state (typically 18-40 years)
- Educational qualifications from 10th to postgraduate level
- Physical standards for police and certain other posts

Application Process:
- Online applications through state portals
- Examination fees vary by state
- Documents often need to be in regional language
- Written exams conducted in regional language and English/Hindi

Advantages:
- Opportunity to work in home state
- Language advantage in communication
- Understanding of local issues and context
- Proximity to family and community

Preparation Tips:
- Study state-specific history, geography, and culture
- Learn regional language if required
- Follow state government policies and schemes
- Understand state administrative structure
- Practice previous year state papers""",
                "short_description": "Information about state government job opportunities and requirements",
                "icon": "map",
                "sort_order": 2,
            },
            {
                "label": "Banking and Financial Sector Jobs",
                "body": """Banking sector jobs are among the most sought-after government positions due to their career growth prospects, decent salaries, and urban postings.

Major Recruiters:
- Public Sector Banks (SBI, PNB, BOB, etc.)
- Regional Rural Banks
- Cooperative Banks
- Insurance companies (LIC, GIC, etc.)
- RBI and NABARD (for specialized roles)
- Other financial institutions

Types of Positions:
- Probationary Officer (PO): Management trainee role
- Clerk: Customer service and administrative work
- Specialist Officer: IT, HR, Marketing, Law, Agriculture, etc.
- Agricultural Field Officer
- Law Officer
- Rajbhasha Adhikari (Hindi language officer)

Recruitment Process:
- IBPS conducts common recruitment for most banks
- SBI conducts its own recruitment
- Selection through: Preliminary Exam → Main Exam → Interview
- Some specialist roles may have additional technical tests

Eligibility:
- Graduate in any discipline for PO and Clerk
- Specialized degrees for Specialist Officer posts
- Age typically 20-30 years (with relaxations)
- Computer literacy is essential
- Good communication skills required

Career Progression:
- Clear promotion exams (JAIIB/CAIIB for banking professionals)
- Performance-based promotions
- Transfer opportunities across India
- Specialization in specific banking functions

Salary and Benefits:
- Competitive starting salary
- Dearness allowance and other perks
- Housing loan facilities at reduced rates
- Medical benefits
- Pension after retirement

Preparation Focus:
- Quantitative aptitude and data interpretation
- Reasoning ability
- English language
- General awareness with banking awareness
- Computer knowledge
- Interview preparation""",
                "short_description": "Overview of banking and financial sector government job opportunities",
                "icon": "landmark",
                "sort_order": 3,
            },
            {
                "label": "Railway Recruitment",
                "body": """Indian Railways is one of the largest employers in the world, offering diverse job opportunities across various departments and categories.

Recruitment through RRB:
- Railway Recruitment Boards conduct centralized recruitment
- Notifications released through CEN (Centralized Employment Notice)
- Online application process through common portal
- Computer-based tests (CBT) for most positions

Job Categories:
NTPC (Non-Technical Popular Categories):
- Graduate level: Goods Train Manager, Station Master, Commercial Supervisor
- Undergraduate level: Clerk, Ticket Collector, Trains Clerk

Group D (Level 1):
- Track maintainer, Pointsman, Helper, Assistant in various departments

Technical Categories:
- Junior Engineer (JE)
- Senior Section Engineer (SSE)
- Loco Pilot
- Technician

Para-Medical and Other Categories:
- Staff Nurse, Pharmacist, Lab Assistant
- Teachers in railway schools
- Catering and hospitality roles

Selection Process:
- CBT (Computer Based Test) - Stage 1 and/or Stage 2
- Skill test (typing for some posts)
- Physical Efficiency Test (PET) for certain categories
- Document verification
- Medical examination

Eligibility:
- Educational qualification varies by post (10th to Graduate)
- Age limits: 18-33 years (category-wise relaxations apply)
- Medical standards vary by post (A1, A2, B1, B2, C1, C2)
- Physical standards for some posts

Benefits:
- Job security with permanent positions
- Free or subsidized travel passes
- Medical facilities
- Quarters or housing allowance
- Children's education benefits
- Pension after retirement

Preparation Tips:
- Focus on technical knowledge for engineering posts
- General awareness and current affairs
- Mathematics and reasoning
- Technical subject-specific preparation
- Physical fitness for posts requiring PET""",
                "short_description": "Comprehensive guide to railway recruitment opportunities and processes",
                "icon": "train",
                "sort_order": 4,
            },
            {
                "label": "Defense and Paramilitary Jobs",
                "body": """Defense and paramilitary services offer prestigious career opportunities for those seeking to serve the nation while enjoying excellent benefits and job security.

Armed Forces:
Indian Army:
- Soldiers (General Duty, Technical, Tradesman)
- Officers through NDA, CDS, TES, UES
- Technical Entry Scheme
- Agniveer scheme (new recruitment model)

Indian Navy:
- Sailors (MR, NMR, SSR, AA)
- Officers through NDA, CDS, INET
- Technical entries

Indian Air Force:
- Airmen (X Group, Y Group)
- Officers through NDA, CDS, AFCAT
- Technical entries

Paramilitary Forces:
- CRPF (Central Reserve Police Force)
- BSF (Border Security Force)
- CISF (Central Industrial Security Force)
- ITBP (Indo-Tibetan Border Police)
- SSB (Sashastra Seema Bal)
- Assam Rifles

Selection Process:
Armed Forces:
- Written examination (for some entries)
- Physical fitness test
- Medical examination
- Interview (SSB for officers)
- Merit list and final selection

Paramilitary:
- Written examination
- Physical efficiency test
- Physical standards test
- Medical examination
- Document verification
- Final merit list

Eligibility:
- Age: 17.5-23 years for most entries
- Educational: 10th/12th/Graduate depending on post
- Physical: Height, chest, weight standards
- Medical: Vision and general fitness requirements

Benefits:
- Excellent pay and allowances
- Pension and retirement benefits
- Free medical facilities for self and family
- Canteen facilities
- Housing accommodation
- Adventure sports opportunities
- Post-retirement benefits

Preparation:
- Physical fitness training
- Written exam preparation (general awareness, reasoning, mathematics)
- SSB interview preparation for officer entries
- Medical fitness maintenance
- Current affairs knowledge""",
                "short_description": "Information about defense and paramilitary job opportunities",
                "icon": "shield",
                "sort_order": 5,
            },
        ]

        for category in categories:
            item, created = ContentItem.objects.get_or_create(
                section=section,
                label=category["label"],
                defaults={
                    "body": category["body"],
                    "short_description": category["short_description"],
                    "icon": category["icon"],
                    "sort_order": category["sort_order"],
                    "is_active": True,
                    "show_on_homepage": True,
                },
            )
            counts["content_items"] += int(created)

    def _seed_study_resources(self, counts):
        """Create study resource and preparation material content."""

        section, created = ContentSection.objects.get_or_create(
            slug="study-resources",
            defaults={
                "area": ContentSection.Area.HOMEPAGE,
                "title": "Study Resources",
                "description": "General study materials and preparation tips",
                "icon": "book-open",
                "sort_order": 30,
                "is_active": True,
            },
        )
        counts["sections"] += int(created)

        resources = [
            {
                "label": "Subject-wise Preparation Strategy",
                "body": """A structured subject-wise approach helps you cover the syllabus effectively:

General Awareness/Current Affairs:
- Read one national newspaper daily (The Hindu, Indian Express)
- Follow government schemes and policies
- Keep track of national and international events
- Focus on last 12 months of current affairs
- Make monthly notes for quick revision
- Use reliable current affairs magazines or websites

Quantitative Aptitude:
- Master basic arithmetic operations
- Learn percentage, ratio, and profit-loss concepts
- Practice time-speed-distance problems
- Work on data interpretation skills
- Learn shortcuts for calculations
- Practice 20-30 questions daily

Reasoning Ability:
- Understand different question types (analogy, classification, series, coding-decoding)
- Practice logical reasoning puzzles
- Work on verbal and non-verbal reasoning
- Improve analytical thinking
- Solve puzzles regularly to enhance skills
- Time yourself while practicing

English Language:
- Build vocabulary through daily reading
- Learn grammar rules systematically
- Practice comprehension passages
- Work on error detection and correction
- Improve sentence arrangement skills
- Practice synonyms and antonyms

General Science:
- Focus on physics, chemistry, and biology basics
- Understand scientific principles behind daily phenomena
- Learn about recent scientific developments
- Study NCERT books for foundational knowledge
- Focus on applications of science in daily life

Computer Knowledge:
- Learn basic computer operations
- Understand MS Office applications
- Study internet and networking basics
- Learn about computer security
- Practice keyboard shortcuts

Remember: Quality of practice matters more than quantity. Focus on understanding concepts rather than rote memorization.""",
                "short_description": "Systematic approach to preparing for different examination subjects",
                "icon": "library",
                "sort_order": 1,
            },
            {
                "label": "Previous Year Papers: How to Use Them Effectively",
                "body": """Previous year question papers are invaluable resources for exam preparation. Here's how to use them effectively:

Why Previous Papers Matter:
- Understand exam pattern and question types
- Identify important topics and their weightage
- Practice time management
- Gauge your preparation level
- Familiarize yourself with difficulty level

How to Use Previous Papers:
1. Start with Recent Papers
- Begin with the last 3-5 years' papers
- Move to older papers for additional practice
- Compare patterns across years

2. Simulate Exam Conditions
- Set a timer matching the actual exam duration
- Sit in a quiet environment
- Use only allowed materials
- Attempt seriously without breaks

3. Analyze Your Performance
- Identify weak areas
- Note frequently asked topics
- Understand question patterns
- Track improvement over time

4. Learn from Mistakes
- Review every incorrect answer
- Understand why you made mistakes
- Learn the correct approach
- Practice similar questions

Tips for Maximum Benefit:
- Solve papers after completing syllabus
- Don't just memorize answers—understand concepts
- Create a question bank from repeated topics
- Discuss difficult questions with peers or mentors
- Maintain a notebook of important questions

Subject-wise Focus:
- For aptitude: Focus on calculation speed
- For reasoning: Practice pattern recognition
- For general awareness: Note recurring themes
- For English: Understand question types

Remember: Previous papers indicate trends, not guarantees. Stay prepared for new patterns too.""",
                "short_description": "Guide to effectively utilizing previous year question papers for preparation",
                "icon": "file-text",
                "sort_order": 2,
            },
            {
                "label": "Mock Tests: Importance and Strategy",
                "body": """Mock tests are essential tools for exam preparation. They simulate the actual exam environment and help you assess your readiness.

Benefits of Mock Tests:
- Real exam experience
- Time management practice
- Performance analysis
- Weakness identification
- Confidence building
- Strategy refinement

How to Approach Mock Tests:
1. Initial Phase (Early Preparation)
- Take 1-2 mock tests per week
- Focus on understanding patterns
- Don't worry about scores initially
- Learn time allocation strategies

2. Intermediate Phase (Mid Preparation)
- Increase frequency to 2-3 per week
- Work on improving weak areas
- Practice different strategies
- Analyze each test thoroughly

3. Final Phase (Last Month)
- Take mock tests daily or every other day
- Simulate exact exam conditions
- Fine-tune your strategy
- Build exam temperament

Analyzing Mock Test Results:
- Review each section's performance
- Identify time-consuming questions
- Note accuracy in different topics
- Understand silly mistakes
- Track improvement trends

Strategic Tips:
- Don't get discouraged by low initial scores
- Focus on improvement, not absolute scores
- Experiment with different attempt orders
- Learn to skip difficult questions
- Maintain accuracy over speed

Common Mistakes to Avoid:
- Taking too many mocks without analysis
- Not learning from mistakes
- Getting demotivated by scores
- Not simulating real conditions
- Ignoring time management

Remember: Mock tests are diagnostic tools, not final predictors. Use them for learning and improvement.""",
                "short_description": "Understanding the role of mock tests in exam preparation and how to use them",
                "icon": "target",
                "sort_order": 3,
            },
        ]

        for resource in resources:
            item, created = ContentItem.objects.get_or_create(
                section=section,
                label=resource["label"],
                defaults={
                    "body": resource["body"],
                    "short_description": resource["short_description"],
                    "icon": resource["icon"],
                    "sort_order": resource["sort_order"],
                    "is_active": True,
                    "show_on_homepage": True,
                },
            )
            counts["content_items"] += int(created)

    def _seed_faq_content(self, counts):
        """Create FAQ-style content for common questions."""

        section, created = ContentSection.objects.get_or_create(
            slug="frequently-asked-questions",
            defaults={
                "area": ContentSection.Area.HOMEPAGE,
                "title": "Frequently Asked Questions",
                "description": "Common questions about government jobs and preparation",
                "icon": "help-circle",
                "sort_order": 40,
                "is_active": True,
            },
        )
        counts["sections"] += int(created)

        faqs = [
            {
                "label": "What is the age limit for government jobs?",
                "body": """Age limits for government jobs vary based on the recruiting organization, category, and position:

General Category:
- Most central government jobs: 18-30 or 18-32 years
- UPSC Civil Services: 21-32 years
- Banking jobs: 20-30 years
- Railway jobs: 18-33 years
- State government jobs: 18-40 years (varies by state)

Reserved Categories:
- OBC: Usually 3 years relaxation
- SC/ST: Usually 5 years relaxation
- PwD: Up to 10 years relaxation
- Ex-servicemen: As per government rules

Age Calculation:
- Age is calculated as on a specific date mentioned in the notification
- This date is usually the application closing date or a specified cutoff date
- Birth certificate or school leaving certificate is required as proof

Important Notes:
- Age relaxation is cumulative for candidates eligible for multiple categories
- Some posts have upper age limits even with relaxation
- Always check the official notification for exact age criteria
- Central government and state government may have different age limits

Tips:
- Start preparation early to utilize maximum attempts
- Be aware of category certificate requirements
- Keep age-proof documents ready
- Check eligibility before applying""",
                "short_description": "Understanding age limits and relaxations for government job applications",
                "icon": "calendar",
                "sort_order": 1,
            },
            {
                "label": "What educational qualifications are required?",
                "body": """Educational requirements vary widely across government jobs. Here's a general overview:

10th Pass (Matriculation):
- Multi-tasking staff in various departments
- Constable and defense positions
- Group D posts in railways
- Peon and support staff roles
- Some technical trades with ITI

12th Pass (Intermediate):
- Clerical positions in many departments
- Lower division clerk (LDC)
- Data entry operator
- Some banking positions
- Police sub-inspector (in some states)
- Defense positions through NDA

Graduate (Any Discipline):
- Civil services (UPSC and state PSCs)
- Banking PO and clerk positions
- SSC CGL and CHSL positions
- Railway NTPC graduate posts
- Teaching positions (with B.Ed)
- Many administrative roles

Professional Degrees:
- Engineering: PSU jobs, engineering services, technical posts
- Medical: Health department positions, medical services
- Law: Legal officer, judicial services
- CA/CS: Financial positions in government departments
- Architecture: CPWD, PWD positions

Technical Qualifications:
- ITI/Diploma: Technical posts in railways, defense, PSUs
- B.Tech/B.E.: Engineering services, technical officer posts
- M.Tech/PhD: Research and development positions

Important Considerations:
- Degree must be from a recognized university
- Some posts require specific percentage marks
- Equivalent qualifications are accepted if recognized
- Distance education degrees are accepted if from UGC-recognized institutions

Always verify:
- Check official notification for exact qualification requirements
- Ensure your degree is recognized
- Verify if specific subjects or specializations are required
- Check if experience is required along with qualification""",
                "short_description": "Educational qualification requirements for different government job categories",
                "icon": "graduation-cap",
                "sort_order": 2,
            },
            {
                "label": "How to apply for government jobs online?",
                "body": """Most government job applications are now submitted online. Here's a step-by-step guide:

Preparation Before Applying:
1. Documents Required:
- Scanned photograph (recent, passport size)
- Scanned signature
- Educational certificates (10th, 12th, degree certificates)
- Category certificate (if applicable)
- ID proof (Aadhaar, PAN card)
- Bank details for fee payment

2. Technical Requirements:
- Computer or smartphone with internet
- Valid email address
- Mobile number for OTP verification
- Scanned documents in specified format (JPEG/PDF)
- Debit card/credit card/net banking for fee payment

Application Process:
1. Registration:
- Visit the official recruitment website
- Create an account with email and mobile
- Fill basic personal details
- Verify email and mobile number

2. Filling the Application Form:
- Enter personal information carefully
- Fill educational qualifications
- Upload required documents
- Select exam center preferences
- Preview and verify all details

3. Fee Payment:
- Pay application fee online
- Save payment confirmation
- Note transaction ID for reference

4. Submission:
- Submit the application after verification
- Download and print the application form
- Save application number for future reference

Important Tips:
- Apply well before the deadline to avoid last-minute issues
- Ensure all documents are within size limits
- Double-check all information before submission
- Use a stable internet connection
- Keep all details recorded safely

Common Issues and Solutions:
- Server overload: Try during off-peak hours
- Document upload failure: Check file size and format
- Payment failure: Try again or use different payment method
- OTP not received: Check mobile network and retry

After Submission:
- Save application number and password
- Download admit card when released
- Check website for updates regularly
- Prepare for the examination""",
                "short_description": "Step-by-step guide for online government job applications",
                "icon": "mouse-pointer",
                "sort_order": 3,
            },
            {
                "label": "What documents are required for document verification?",
                "body": """Document verification is a crucial stage in the selection process. Here's a comprehensive list of commonly required documents:

Essential Documents (Always Required):
1. Identity Proof:
- Aadhaar card (mandatory in most cases)
- PAN card
- Voter ID card
- Passport (if available)

2. Age Proof:
- Birth certificate
- School leaving certificate (10th marksheet with DOB)
- Any other government-issued age certificate

3. Educational Documents:
- 10th certificate and marksheet
- 12th certificate and marksheet
- Degree certificate and marksheet
- Semester-wise marksheet (if applicable)
- Migration certificate (if required)

4. Category Certificates (if applicable):
- Caste certificate for SC/ST/OBC
- EWS certificate (Economically Weaker Sections)
- Income certificate (for fee relaxation)

5. Other Important Documents:
- Recent passport-size photographs
- Signature scanned copy
- Disability certificate (for PwD category)
- Ex-serviceman certificate (if applicable)
- No-objection certificate (for employed candidates)

Documents for Specific Posts:
- For Technical Posts: ITI/Diploma/Engineering degree certificates
- For Teaching Posts: B.Ed/M.Ed certificates, CTET/STET qualification
- For Defense Posts: Physical fitness certificates, character certificate
- For Banking Posts: Graduation certificate, computer literacy certificate

Document Guidelines:
- All documents should be self-attested
- Carry both original and photocopies
- Documents should be in date (not expired)
- Name should match across all documents
- Address proof should be current

Tips for Document Verification:
- Organize documents in a folder beforehand
- Carry extra photocopies
- Ensure all certificates are from recognized institutions
- Get category certificates made well in advance
- Check specific requirements in the official notification

Common Issues:
- Name mismatch across documents: Get an affidavit
- Missing certificates: Apply for duplicates from issuing authority
- Category certificate disputes: Verify from competent authority
- Date of birth variations: Provide proof with earliest document""",
                "short_description": "Complete list of documents required for government job document verification",
                "icon": "folder",
                "sort_order": 4,
            },
        ]

        for faq in faqs:
            item, created = ContentItem.objects.get_or_create(
                section=section,
                label=faq["label"],
                defaults={
                    "body": faq["body"],
                    "short_description": faq["short_description"],
                    "icon": faq["icon"],
                    "sort_order": faq["sort_order"],
                    "is_active": True,
                    "show_on_homepage": True,
                },
            )
            counts["content_items"] += int(created)
