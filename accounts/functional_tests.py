"""
Functional Tests for Critical Routes and Workflows
Tests public routes, authentication, forms, and permissions
"""
from django.test import Client, TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from jobs.models import Job

User = get_user_model()


class PublicRouteTests(TestCase):
    """Test all public routes return correct HTTP status codes"""

    def setUp(self):
        self.client = Client()

    def test_homepage_loads(self):
        """Homepage should load successfully"""
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)

    def test_jobs_list_loads(self):
        """Jobs listing page should load"""
        response = self.client.get(reverse('jobs:list'))
        self.assertEqual(response.status_code, 200)

    def test_tools_index_loads(self):
        """Tools index page should load"""
        response = self.client.get(reverse('tools'))
        self.assertEqual(response.status_code, 200)

    def test_comments_list_loads(self):
        """Comments page should load"""
        response = self.client.get(reverse('comments:list'))
        self.assertEqual(response.status_code, 200)

    def test_eligibility_checker_loads(self):
        """Eligibility checker page should load"""
        response = self.client.get(reverse('jobs:eligibility_check'))
        self.assertEqual(response.status_code, 200)

    def test_image_resizer_loads(self):
        """Image resizer tool should load"""
        response = self.client.get(reverse('tools_image_resizer'))
        self.assertEqual(response.status_code, 200)

    def test_jpg_to_pdf_loads(self):
        """JPG to PDF tool should load"""
        response = self.client.get(reverse('tools_jpg_to_pdf'))
        self.assertEqual(response.status_code, 200)

    def test_photo_name_date_loads(self):
        """Photo name date tool should load"""
        response = self.client.get(reverse('tools_photo_name_date'))
        self.assertEqual(response.status_code, 200)

    def test_photo_signature_joiner_loads(self):
        """Photo signature joiner tool should load"""
        response = self.client.get(reverse('tools_photo_signature_joiner'))
        self.assertEqual(response.status_code, 200)

    def test_resume_cv_photo_loads(self):
        """Resume CV photo tool should load"""
        response = self.client.get(reverse('tools_resume_cv_photo'))
        self.assertEqual(response.status_code, 200)

    def test_password_reset_loads(self):
        """Password reset page should load"""
        response = self.client.get(reverse('accounts:password_reset'))
        self.assertEqual(response.status_code, 200)

    def test_login_page_loads(self):
        """Login page should load (django-allauth)"""
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)

    def test_signup_page_loads(self):
        """Signup page should load (django-allauth)"""
        response = self.client.get(reverse('accounts:signup'))
        self.assertEqual(response.status_code, 200)

    def test_cms_requires_auth(self):
        """CMS dashboard should redirect to CMS login for unauthenticated users"""
        response = self.client.get(reverse('site_management:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('site_management:login')))

    def test_admin_requires_auth(self):
        """Django admin should redirect to login for unauthenticated users"""
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/admin/login/'))


class AuthenticationTests(TestCase):
    """Test authentication flows"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_login_page_accessible(self):
        """Login page is accessible"""
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)

    def test_logout(self):
        """User can logout"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('accounts:logout'), follow=True)
        self.assertFalse(response.context['user'].is_authenticated)


class JobSearchTests(TestCase):
    """Test job search and filtering"""

    def setUp(self):
        self.client = Client()
        self.job1 = Job.objects.create(
            title='Software Engineer',
            organization='Tech Corp',
            qualification='B.Tech',
            location='Delhi',
            status='published',
            is_verified=True,
            is_expired=False,
            created_at=timezone.now()
        )
        self.job2 = Job.objects.create(
            title='Data Analyst',
            organization='Data Inc',
            qualification='M.Sc',
            location='Mumbai',
            status='published',
            is_verified=True,
            is_expired=False,
            created_at=timezone.now()
        )

    def test_jobs_list_shows_published_jobs(self):
        """Published jobs appear in listing"""
        response = self.client.get(reverse('jobs:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Software Engineer')
        self.assertContains(response, 'Data Analyst')

    def test_job_search_by_keyword(self):
        """Search filters jobs by keyword"""
        response = self.client.get(reverse('jobs:list'), {'q': 'Software'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Software Engineer')
        self.assertNotContains(response, 'Data Analyst')

    def test_job_detail_loads(self):
        """Job detail page loads for published job"""
        response = self.client.get(reverse('jobs:detail', kwargs={'pk': self.job1.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Software Engineer')


class EligibilityCheckerTests(TestCase):
    """Test eligibility checker form"""

    def setUp(self):
        self.client = Client()
        self.job = Job.objects.create(
            title='Clerk Position',
            organization='Gov Dept',
            qualification='12th Pass',
            location='All India',
            min_age=18,
            max_age=30,
            status='published',
            is_verified=True,
            is_expired=False,
            created_at=timezone.now()
        )

    def test_eligibility_form_loads(self):
        """Eligibility checker form loads"""
        response = self.client.get(reverse('jobs:eligibility_check'))
        self.assertEqual(response.status_code, 200)

    def test_eligibility_check_with_valid_data(self):
        """Eligibility check processes valid data"""
        response = self.client.post(
            reverse('jobs:eligibility_check'),
            {
                'age': 25,
                'qualification': '12th Pass',
            }
        )
        self.assertEqual(response.status_code, 200)


class CommentsTests(TestCase):
    """Test comments functionality"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='commenter',
            email='commenter@example.com',
            password='testpass123'
        )

    def test_unauthenticated_user_cannot_post_comment(self):
        """Unauthenticated users cannot post comments"""
        response = self.client.post(
            reverse('comments:list'),
            {'body': 'Test comment'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('accounts:login')) or response.url.startswith('/accounts/login/'))

    def test_authenticated_user_can_view_comment_form(self):
        """Authenticated users see comment form"""
        self.client.login(username='commenter', password='testpass123')
        response = self.client.get(reverse('comments:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Leave a comment')


class CMSPersistenceTests(TestCase):
    """Test CMS settings persistence"""

    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass123'
        )

    def test_cms_settings_page_loads_for_admin(self):
        """CMS settings page loads for admin user"""
        self.client.login(username='admin', password='adminpass123')
        response = self.client.get(reverse('site_management:settings'))
        self.assertEqual(response.status_code, 200)

    def test_cms_settings_save_and_persist(self):
        """CMS settings save and persist after reload"""
        from site_management.models import WebsiteSettings

        self.client.login(username='admin', password='adminpass123')

        # Get initial settings
        settings = WebsiteSettings.objects.first()
        if not settings:
            settings = WebsiteSettings.objects.create(
                site_name='Initial Site',
                tagline='Initial Tagline'
            )

        # Update settings via POST - only send fields that are definitely in the form
        response = self.client.post(
            reverse('site_management:settings'),
            {
                'site_name': 'Updated Test Site',
                'tagline': 'Updated Test Tagline',
            },
            follow=True
        )
        
        # Check if request was successful
        self.assertEqual(response.status_code, 200)

        # Verify persistence - refresh from DB
        settings.refresh_from_db()
        self.assertEqual(settings.site_name, 'Updated Test Site')
        self.assertEqual(settings.tagline, 'Updated Test Tagline')
