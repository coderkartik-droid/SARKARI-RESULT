from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser
from accounts.views import website_page
import re

factory = RequestFactory()

# GET request
req = factory.get('/contact-us/')
req.user = AnonymousUser()
# Django middleware not invoked in RequestFactory, add session manually
from django.contrib.sessions.backends.db import SessionStore
req.session = SessionStore()
from django.contrib.messages.storage.fallback import FallbackStorage
req._messages = FallbackStorage(req)

response = website_page(req, page_type='contact_us')
html = response.content.decode()

checks = [
    ('HTTP 200',                            response.status_code == 200),
    ('Contact Us h1',                       'Contact Us' in html),
    ('contact-page class',                  'contact-page' in html),
    ('contact form present',                'contact-form' in html),
    ('CSRF token',                          'csrfmiddlewaretoken' in html),
    ('name field',                          'id_name' in html or 'name="name"' in html),
    ('email field',                         'id_email' in html or 'name="email"' in html),
    ('subject field',                       'id_subject' in html or 'name="subject"' in html),
    ('message field',                       'id_message' in html or 'name="message"' in html),
    ('honeypot present',                    'portal-honeypot' in html),
    ('submit button',                       'Send message' in html),
    ('info cards present',                  'contact-info-card' in html),
    ('General Enquiries',                   'General Enquiries' in html),
    ('Report Incorrect',                    'Report Incorrect' in html),
    ('Suggestions card',                    'Suggestions' in html),
    ('no placeholder email shown',          'you@example.com' in html),  # placeholder attr OK
    ('no hardcoded contact address',        'office address' not in html.lower()),
    ('no duplicate navbar',                 html.count('portal-header') <= 1),
    ('contact-submit-btn',                  'contact-submit-btn' in html),
]
print("CONTACT PAGE RENDER CHECKS")
print("=" * 50)
for label, result in checks:
    print(f"  {'[OK]  ' if result else '[FAIL] '}{label}")
