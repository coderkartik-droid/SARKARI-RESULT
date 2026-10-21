from django.contrib import admin
from django.conf import settings
from django.http import JsonResponse
from django.urls import include, path
from django.conf.urls.static import static
from django.views.decorators.http import require_GET

from accounts import views


@require_GET
def health_check(request):
    """Lightweight, read-only liveness probe.

    Returns a fixed payload only: no configuration, credentials or error
    detail is ever included.
    """
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    # Both forms are registered so neither relies on an APPEND_SLASH redirect.
    path("health", health_check, name="health"),
    path("health/", health_check, name="health_slash"),
    path("accounts/", include(("accounts.urls", "accounts"), namespace="accounts")),
    path("accounts/", include("allauth.socialaccount.providers.google.urls")),
    path("accounts/", include("allauth.socialaccount.urls")),
    path("comments/", include(("comments.urls", "comments"), namespace="comments")),
    path("api/ai/", include("ai_assistant.urls")),
    path("jobs/", include("jobs.urls")),
    path(
        "site-management/",
        include(("site_management.urls", "site_management"), namespace="site_management"),
    ),
    path("tools/", views.tools, name="tools"),
    path("tools/image-resizer/", views.tools_image_resizer, name="tools_image_resizer"),
    path("tools/jpg-to-pdf/", views.tools_jpg_to_pdf, name="tools_jpg_to_pdf"),
    path("tools/photo-name-date/", views.tools_photo_name_date, name="tools_photo_name_date"),
    path("tools/photo-signature-joiner/", views.tools_photo_signature_joiner, name="tools_photo_signature_joiner"),
    path("tools/resume-cv-photo/", views.tools_resume_cv_photo, name="tools_resume_cv_photo"),
    path("about-us/", views.website_page, {"page_type": "about_us"}, name="about_us"),
    path("contact-us/", views.website_page, {"page_type": "contact_us"}, name="contact_us"),
    path("privacy-policy/", views.website_page, {"page_type": "privacy_policy"}, name="privacy_policy"),
    path("terms-and-conditions/", views.website_page, {"page_type": "terms_and_conditions"}, name="terms_and_conditions"),
    path("disclaimer/", views.website_page, {"page_type": "disclaimer"}, name="disclaimer"),
    path("content-details/", views.website_page, {"page_type": "content_details"}, name="content_details"),
    path("", views.home, name="home"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
