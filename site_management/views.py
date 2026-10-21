from datetime import timedelta
from types import SimpleNamespace

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.forms import formset_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST

from ai_assistant.models import AIDailyUsage
from comments.models import Comment
from .forms import (
    AnswerSheetForm,
    ContentItemForm,
    ContentLinkForm,
    ContentSectionForm,
    ExamForm,
    ExamPDFForm,
    ManagementUserEditForm,
    PreviousPaperForm,
    RegistrationResourceForm,
    ResourceURLForm,
    ResultForm,
    SocialMediaProfileForm,
    WebsitePageCreateForm,
    WebsitePageForm,
    WebsiteSettingsForm,
)
from .models import (
    AnswerSheet,
    ContactSubmission,
    ContentItem,
    ContentLink,
    ContentSection,
    DEFAULT_SOCIAL_PROFILE_SETTINGS,
    Exam,
    ExamPDF,
    PreviousPaper,
    RegistrationResource,
    ResourceURL,
    Result,
    SocialMediaProfile,
    WebsiteSettings,
    WebsitePage,
)
from .navigation import build_navigation, sidebar_stats


def staff_required(view):
    return user_passes_test(
        lambda user: user.is_active and (user.is_staff or user.is_superuser),
        login_url="site_management:login",
    )(view)


class StaffAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not (user.is_staff or user.is_superuser):
            raise ValidationError(
                "This account is not authorized to manage the site.",
                code="staff_required",
            )


class ManagementLoginView(LoginView):
    template_name = "site_management/login.html"
    authentication_form = StaffAuthenticationForm
    redirect_authenticated_user = False
    next_page = reverse_lazy("site_management:dashboard")

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session.set_expiry(None)
        return response

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and (
            request.user.is_staff or request.user.is_superuser
        ):
            return redirect("site_management:dashboard")
        return super().dispatch(request, *args, **kwargs)


@staff_required
@require_POST
def management_logout(request):
    logout(request)
    return redirect("site_management:login")


AREA_DESCRIPTIONS = {
    ContentSection.Area.NAVIGATION: "Main menus, dropdowns, and header links shown at the top of every page.",
    ContentSection.Area.HOMEPAGE: "Homepage content blocks and the listing sections visitors browse.",
    ContentSection.Area.ANNOUNCEMENTS: "Announcement and notice strip entries near the top of the homepage.",
    ContentSection.Area.HERO_ACTIONS: "Optional buttons and links displayed inside the homepage hero.",
    ContentSection.Area.TOOLS: "The public Photo Tools landing page: its heading, introduction, and cards for existing tools. Tool routes and processing remain fixed.",
    ContentSection.Area.FOOTER: "Footer columns, contact details, and social links shown at the bottom.",
}

AREA_PUBLIC_URLS = {
    ContentSection.Area.NAVIGATION: "home",
    ContentSection.Area.HOMEPAGE: "home",
    ContentSection.Area.ANNOUNCEMENTS: "home",
    ContentSection.Area.HERO_ACTIONS: "home",
    ContentSection.Area.TOOLS: "tools",
    ContentSection.Area.FOOTER: "home",
}

PAGE_ROUTE_NAMES = {
    WebsitePage.PageType.ABOUT_US: "about_us",
    WebsitePage.PageType.CONTACT_US: "contact_us",
    WebsitePage.PageType.PRIVACY_POLICY: "privacy_policy",
    WebsitePage.PageType.TERMS_AND_CONDITIONS: "terms_and_conditions",
    WebsitePage.PageType.DISCLAIMER: "disclaimer",
    WebsitePage.PageType.CONTENT_DETAILS: "content_details",
}


@staff_required
def dashboard(request):
    return render(
        request,
        "site_management/dashboard.html",
        {
            "stats": _dashboard_stats(),
            "is_superuser": request.user.is_superuser,
        },
    )


@staff_required
def section_overview(request, section):
    """Landing page for a top-level workspace section.

    Sections that map straight to a single screen (Users, AI Assistant,
    Comments) redirect there instead of rendering an empty overview.
    """
    sections = build_navigation(
        request.user, current_path=request.path, stats=sidebar_stats()
    )
    data = next(
        (item for item in sections if item["key"] == section),
        None,
    )
    if data is None:
        raise Http404("Unknown management section.")
    if not data["has_submenu"]:
        return redirect(data["url"])
    return render(
        request,
        "site_management/section_overview.html",
        {"section": data},
    )


def _dashboard_stats():
    try:
        pending_comments = Comment.objects.filter(status=Comment.Status.PENDING).count()
    except Exception:
        pending_comments = 0
    ai_enabled = bool(getattr(settings, "AI_ENABLED", False))
    resources_published = sum(
        model.objects.filter(status="published", is_active=True).count()
        for model in (AnswerSheet, RegistrationResource, PreviousPaper, Result)
    )
    return {
        "exams_published": Exam.objects.filter(
            status=Exam.Status.PUBLISHED, is_active=True
        ).count(),
        "resources_published": resources_published,
        "contact_unread": ContactSubmission.objects.filter(is_read=False).count(),
        "pending_comments": pending_comments,
        "ai_enabled": ai_enabled,
    }


@staff_required
def area_manager(request, area):
    if area not in dict(ContentSection.Area.choices):
        raise Http404("Unknown content area.")
    sections = list(
        ContentSection.objects.filter(area=area).prefetch_related(
            Prefetch(
                "items",
                queryset=ContentItem.objects.filter(parent__isnull=True).prefetch_related(
                    "children"
                ),
            )
        )
    )
    public_url = reverse(AREA_PUBLIC_URLS[area])
    return render(
        request,
        "site_management/area_manager.html",
        {
            "area": area,
            "area_label": dict(ContentSection.Area.choices)[area],
            "area_description": AREA_DESCRIPTIONS.get(area, ""),
            "sections": sections,
            "item_count": sum(len(section.items.all()) for section in sections),
            "add_section_url": f"{reverse('site_management:section_create')}?area={area}",
            "public_url": public_url,
        },
    )


@staff_required
def settings_edit(request):
    instance = WebsiteSettings.objects.first() or WebsiteSettings()
    form = WebsiteSettingsForm(
        request.POST or None,
        instance=instance,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
        messages.success(request, "General website settings saved.")
        return redirect("site_management:settings")
    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "page_title": "General settings",
            "back_url": reverse("site_management:dashboard"),
            "submit_label": "Save settings",
            "public_url": reverse("home"),
            "form_description": "These values control the public brand, homepage hero, and footer. Exact destinations are noted beside each field.",
        },
    )


@staff_required
def section_create(request):
    initial = {}
    requested_area = request.GET.get("area", "")
    has_area_context = requested_area in ContentSection.Area.values
    if has_area_context:
        initial["area"] = requested_area
    form = ContentSectionForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            section = form.save()
        messages.success(request, f'"{section.title}" section created.')
        return redirect("site_management:area_manager", area=section.area)
    public_url = (
        reverse(AREA_PUBLIC_URLS[requested_area])
        if has_area_context and requested_area in AREA_PUBLIC_URLS
        else reverse("home")
    )
    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "page_title": "Create a content section",
            "back_url": (
                reverse("site_management:area_manager", args=[requested_area])
                if has_area_context
                else reverse("site_management:dashboard")
            ),
            "submit_label": "Create section",
            "public_url": public_url,
            "form_description": "Choose the public area this section belongs to. Its title and description are shown in that area; for Tools, the section controls the Tools landing-page heading and introduction.",
        },
    )


@staff_required
def section_edit(request, section_id):
    section = get_object_or_404(ContentSection, pk=section_id)
    form = ContentSectionForm(request.POST or None, instance=section)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
        messages.success(request, f'"{section.title}" section updated.')
        return redirect("site_management:area_manager", area=section.area)
    public_url = None
    if section.is_active:
        if section.area == ContentSection.Area.HOMEPAGE:
            public_url = reverse("accounts:section_list", args=[section.slug])
        elif section.area in AREA_PUBLIC_URLS:
            public_url = reverse(AREA_PUBLIC_URLS[section.area])
    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "page_title": f"Edit {section.title}",
            "back_url": reverse("site_management:area_manager", args=[section.area]),
            "submit_label": "Save section",
            "public_url": public_url,
            "form_description": f"Public location: {section.get_area_display()}. Title and description are displayed in this area; the active switch controls public visibility.",
        },
    )


@staff_required
def section_delete(request, section_id):
    section = get_object_or_404(ContentSection, pk=section_id)
    if request.method == "POST":
        title = section.title
        area = section.area
        with transaction.atomic():
            section.delete()
        messages.success(request, f'"{title}" section and its items were deleted.')
        return redirect("site_management:area_manager", area=area)
    return render(
        request,
        "site_management/confirm_delete.html",
        {
            "object_label": section.title,
            "back_url": reverse("site_management:dashboard"),
            "warning": "Deleting a section also removes all of its content and links.",
        },
    )


@staff_required
def item_create(request, section_id):
    section = get_object_or_404(ContentSection, pk=section_id)
    form = ContentItemForm(
        request.POST or None,
        request.FILES or None,
        section=section,
        initial={"section": section},
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            item = form.save(commit=False)
            item.section = section
            item.save()
        item_title = item.label or (item.body[:35] + "..." if len(item.body) > 35 else item.body) or "Content block"
        messages.success(request, f'"{item_title}" was added.')
        return redirect("site_management:area_manager", area=section.area)
    public_url = None
    if section.is_active:
        if section.area == ContentSection.Area.HOMEPAGE:
            public_url = reverse("accounts:section_list", args=[section.slug])
        elif section.area in AREA_PUBLIC_URLS:
            public_url = reverse(AREA_PUBLIC_URLS[section.area])
    if section.area == ContentSection.Area.HOMEPAGE:
        form_description = (
            f"Public location: Homepage → {section.title}. "
            "Note: The public homepage displays the 2 newest items in this section box; "
            "all active items remain accessible to visitors in the section archive."
        )
    else:
        form_description = (
            f"Public location: {section.get_area_display()} → {section.title}. "
            "Each field describes where its value appears. For Tools, choose a fixed existing tool destination."
        )
    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "page_title": f"Add an item to {section.title}",
            "back_url": reverse("site_management:area_manager", args=[section.area]),
            "submit_label": "Add item",
            "public_url": public_url,
            "form_description": form_description,
        },
    )


@staff_required
def item_edit(request, item_id):
    item = get_object_or_404(ContentItem.objects.select_related("section"), pk=item_id)
    form = ContentItemForm(
        request.POST or None,
        request.FILES or None,
        instance=item,
        section=item.section,
        initial={"section": item.section},
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
        item_title = item.label or (item.body[:35] + "..." if len(item.body) > 35 else item.body) or "Content block"
        messages.success(request, f'"{item_title}" was updated.')
        return redirect("site_management:area_manager", area=item.section.area)
    item_title = item.label or (item.body[:35] + "..." if len(item.body) > 35 else item.body) or "Content block"
    public_url = None
    if item.section.is_active and item.is_active:
        if item.section.area == ContentSection.Area.HOMEPAGE:
            if item.parent_id is None:
                public_url = reverse("accounts:section_item_detail", args=[item.section.slug, item.pk])
            else:
                public_url = reverse("accounts:section_list", args=[item.section.slug])
        elif item.section.area == ContentSection.Area.TOOLS and item.url:
            public_url = item.url
        elif item.section.area in AREA_PUBLIC_URLS:
            public_url = reverse(AREA_PUBLIC_URLS[item.section.area])
    if item.section.area == ContentSection.Area.HOMEPAGE:
        form_description = (
            f"Public location: {item.location_path}. "
            "Note: The public homepage displays the 2 newest items in this section box; "
            "all active items remain accessible to visitors in the section archive."
        )
    else:
        form_description = (
            f"Public location: {item.location_path}. "
            "Saved content appears in the matching public section when active and within its publishing window."
        )
    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "page_title": f"Edit {item_title}",
            "back_url": reverse("site_management:area_manager", args=[item.section.area]),
            "submit_label": "Save item",
            "public_url": public_url,
            "form_description": form_description,
        },
    )


@staff_required
def item_delete(request, item_id):
    item = get_object_or_404(ContentItem, pk=item_id)
    item_title = item.label or (item.body[:35] + "..." if len(item.body) > 35 else item.body) or "Content block"
    if request.method == "POST":
        area = item.section.area
        with transaction.atomic():
            item.delete()
        messages.success(request, f'"{item_title}" and its nested items were deleted.')
        return redirect("site_management:area_manager", area=area)
    return render(
        request,
        "site_management/confirm_delete.html",
        {
            "object_label": item_title,
            "back_url": reverse("site_management:dashboard"),
            "warning": "Deleting this item also removes any nested menu items.",
        },
    )


@staff_required
def website_pages_list(request):
    pages = WebsitePage.objects.all()
    for page in pages:
        page.public_url = reverse(PAGE_ROUTE_NAMES[page.page_type])
    existing_types = set(pages.values_list("page_type", flat=True))
    missing_page_types = [
        (page_type, label)
        for page_type, label in WebsitePage.PageType.choices
        if page_type not in existing_types
    ]
    return render(
        request,
        "site_management/website_pages_list.html",
        {
            "pages": pages,
            "missing_page_types": missing_page_types,
        },
    )


@staff_required
def website_page_create(request):
    form = WebsitePageCreateForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            page = form.save()
        messages.success(request, f'"{page.title}" page created.')
        return redirect("site_management:website_pages")
    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "page_title": "Create a public page",
            "back_url": reverse("site_management:website_pages"),
            "submit_label": "Create page",
            "form_description": "Choose one supported public route that does not already have a page record. The route itself remains fixed; this creates its editable content.",
        },
    )


@staff_required
def contact_messages(request):
    page = Paginator(
        ContactSubmission.objects.order_by("-created_at", "-pk"),
        25,
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "site_management/contact_messages.html",
        {"page_obj": page},
    )


@staff_required
def contact_message_detail(request, message_id):
    submission = get_object_or_404(ContactSubmission, pk=message_id)
    return render(
        request,
        "site_management/contact_message_detail.html",
        {"submission": submission},
    )


@staff_required
def website_page_edit(request, page_id):
    page = get_object_or_404(WebsitePage, pk=page_id)
    form = WebsitePageForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
        instance=page,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            page = form.save()
        messages.success(request, f'"{page.title}" page updated.')
        return redirect("site_management:website_pages")
    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "page_title": f"Edit {page.title}",
            "public_url": reverse(PAGE_ROUTE_NAMES[page.page_type]),
            "back_url": reverse("site_management:website_pages"),
            "submit_label": "Save page",
            "form_description": f"Public location: {reverse(PAGE_ROUTE_NAMES[page.page_type])}. This editor changes the page content only; existing route and access rules remain unchanged.",
        },
    )


@staff_required
def content_links(request):
    links = ContentLink.objects.select_related(
        "content_item", "content_item__section"
    ).order_by("content_item__section__area", "content_item__section__sort_order",
               "content_item__sort_order", "display_order", "pk")
    return render(
        request,
        "site_management/content_links.html",
        {"links": links},
    )


@staff_required
def content_link_create(request):
    initial = {}
    context_item = None
    item_id = request.GET.get("content_item")
    if item_id and item_id.isdigit():
        context_item = get_object_or_404(
            ContentItem.objects.select_related("section"),
            pk=int(item_id),
            parent__isnull=True,
        )
        initial["content_item"] = context_item
    form = ContentLinkForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            link = form.save()
        messages.success(request, f'"{link.label}" link created.')
        if context_item:
            return redirect(
                "site_management:area_manager",
                area=link.content_item.section.area,
            )
        return redirect("site_management:content_links")
    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "page_title": "Add a content link",
            "back_url": (
                reverse(
                    "site_management:area_manager",
                    args=[context_item.section.area],
                )
                if context_item
                else reverse("site_management:content_links")
            ),
            "submit_label": "Create link",
            "form_description": "Public location: the selected parent content block. This creates one independently scheduled public link; it does not replace the parent block's existing destination.",
        },
    )


@staff_required
def content_link_edit(request, link_id):
    link = get_object_or_404(ContentLink.objects.select_related("content_item__section"), pk=link_id)
    form = ContentLinkForm(request.POST or None, instance=link)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            link = form.save()
        messages.success(request, f'"{link.label}" link updated.')
        return redirect("site_management:content_links")
    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "page_title": f"Edit link: {link.label}",
            "back_url": reverse("site_management:content_links"),
            "submit_label": "Save link",
            "form_description": f"Public location: {link.content_item.location_path}. Start/end times control when this link is visible.",
        },
    )


@staff_required
def content_link_delete(request, link_id):
    link = get_object_or_404(ContentLink, pk=link_id)
    if request.method == "POST":
        label = link.label
        with transaction.atomic():
            link.delete()
        messages.success(request, f'"{label}" link deleted.')
        return redirect("site_management:content_links")
    return render(
        request,
        "site_management/confirm_delete.html",
        {
            "object_label": link.label,
            "back_url": reverse("site_management:content_links"),
            "warning": "Only this additional link will be removed. Its parent content item and its primary destination will remain.",
        },
    )


EXAM_MANAGEMENT_PAGE_SIZE = 20


def _exam_management_rows(kind="all"):
    """Exam rows for the workspace, optionally limited to upcoming/recent exams.

    Upcoming exams are those whose ``exam_date`` is today or later; recent exams
    are those whose ``exam_date`` is before today. Exams without an exam date are
    only listed in the "all" view because they cannot be classified by date.
    """
    today = timezone.localdate()
    rows = Exam.objects.prefetch_related(
        "pdfs", "eligible_qualifications"
    ).order_by("sort_order", "-created_at")
    if kind == "upcoming":
        rows = rows.filter(exam_date__gte=today)
    elif kind == "recent":
        rows = rows.filter(exam_date__lt=today)
    return rows


def _render_exams_list(request, kind):
    exams = _exam_management_rows(kind)
    query = request.GET.get("q", "").strip()[:120]
    if query:
        exams = exams.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
    total_count = exams.count()
    page = Paginator(exams, EXAM_MANAGEMENT_PAGE_SIZE).get_page(request.GET.get("page"))
    headings = {
        "all": ("EXAM ANNOUNCEMENTS", "Exams"),
        "upcoming": ("UPCOMING EXAMS", "Upcoming exams"),
        "recent": ("RECENT EXAMS", "Recent exams"),
    }
    eyebrow, title = headings[kind]
    return render(
        request,
        "site_management/exams.html",
        {
            "exam_kind": kind,
            "eyebrow": eyebrow,
            "page_heading": title,
            "page_obj": page,
            "query": query,
            "total_count": total_count,
            "exam_date_label": {
                "all": "Exam date",
                "upcoming": "Upcoming on",
                "recent": "Held on",
            }[kind],
        },
    )


@staff_required
def exams(request):
    return _render_exams_list(request, "all")


@staff_required
def upcoming_exams(request):
    return _render_exams_list(request, "upcoming")


@staff_required
def recent_exams(request):
    return _render_exams_list(request, "recent")


@staff_required
def exam_create(request):
    form = ExamForm(request.POST or None)
    url_formset = None
    if request.method == "POST":
        url_formset = _get_resource_urls_formset(None, request.POST)
        if form.is_valid() and url_formset.is_valid():
            with transaction.atomic():
                exam = form.save()
                _save_resource_urls(exam, url_formset)
            messages.success(
                request, f'"{exam.title}" exam created. Attach its PDF files below.'
            )
            return redirect("site_management:exam_pdfs", exam_id=exam.pk)
    else:
        url_formset = _get_resource_urls_formset(None)
    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "url_formset": url_formset,
            "page_title": "Add an exam",
            "back_url": reverse("site_management:exams"),
            "submit_label": "Create exam",
            "form_description": "Public location: the Exams page and the Exams box on the homepage. After saving you can attach PDF files to this exam.",
        },
    )


@staff_required
def exam_edit(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    form = ExamForm(request.POST or None, instance=exam)
    url_formset = None
    if request.method == "POST":
        url_formset = _get_resource_urls_formset(exam, request.POST)
        if form.is_valid() and url_formset.is_valid():
            with transaction.atomic():
                exam = form.save()
                _save_resource_urls(exam, url_formset)
            messages.success(request, f'"{exam.title}" exam updated.')
            return redirect("site_management:exams")
    else:
        url_formset = _get_resource_urls_formset(exam)
    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "url_formset": url_formset,
            "page_title": f"Edit exam: {exam.title}",
            "back_url": reverse("site_management:exams"),
            "submit_label": "Save exam",
            "public_url": reverse("accounts:exams") if exam.is_published else "",
            "form_description": "Public location: the Exams page and the Exams box on the homepage. Manage this exam's PDF files from the Exams list.",
        },
    )


@staff_required
def exam_delete(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    if request.method == "POST":
        title = exam.title
        with transaction.atomic():
            exam.delete()
        messages.success(request, f'"{title}" exam deleted.')
        return redirect("site_management:exams")
    return render(
        request,
        "site_management/confirm_delete.html",
        {
            "object_label": exam.title,
            "back_url": reverse("site_management:exams"),
            "warning": "The exam and every PDF attached to it will be removed from the public website.",
        },
    )


@staff_required
def exam_pdfs(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    pdfs = exam.pdfs.order_by("sort_order", "-created_at")
    return render(
        request,
        "site_management/exam_pdfs.html",
        {"exam": exam, "pdfs": pdfs},
    )


@staff_required
def exam_pdf_create(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    form = ExamPDFForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            pdf = form.save(commit=False)
            pdf.exam = exam
            pdf.save()
        messages.success(
            request, f'"{pdf.display_name}" attached to "{exam.title}".'
        )
        return redirect("site_management:exam_pdfs", exam_id=exam.pk)
    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "page_title": f"Add a PDF to {exam.title}",
            "back_url": reverse("site_management:exam_pdfs", args=[exam.pk]),
            "submit_label": "Attach PDF",
            "form_description": f"Public location: the exam card for “{exam.title}” on the Exams page and the homepage. PDF only, maximum 20 MB.",
        },
    )


@staff_required
def exam_pdf_edit(request, pdf_id):
    pdf = get_object_or_404(ExamPDF.objects.select_related("exam"), pk=pdf_id)
    form = ExamPDFForm(request.POST or None, request.FILES or None, instance=pdf)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            current_file = pdf.pdf_file
            saved = form.save(commit=False)
            if not form.cleaned_data.get("pdf_file"):
                saved.pdf_file = current_file
            saved.save()
        messages.success(request, f'"{saved.display_name}" updated.')
        return redirect("site_management:exam_pdfs", exam_id=pdf.exam_id)
    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "page_title": f"Edit PDF: {pdf.display_name}",
            "back_url": reverse("site_management:exam_pdfs", args=[pdf.exam_id]),
            "submit_label": "Save PDF",
            "form_description": f"Attached to the exam “{pdf.exam.title}”. Leave the PDF file empty to keep the current file.",
        },
    )


@staff_required
def exam_pdf_delete(request, pdf_id):
    pdf = get_object_or_404(ExamPDF.objects.select_related("exam"), pk=pdf_id)
    if request.method == "POST":
        label = pdf.display_name
        exam_id = pdf.exam_id
        with transaction.atomic():
            pdf.delete()
        messages.success(request, f'"{label}" PDF deleted.')
        return redirect("site_management:exam_pdfs", exam_id=exam_id)
    return render(
        request,
        "site_management/confirm_delete.html",
        {
            "object_label": pdf.display_name,
            "back_url": reverse("site_management:exam_pdfs", args=[pdf.exam_id]),
            "warning": "This PDF download link will be removed from the exam card on the public website.",
        },
    )


RESOURCE_MANAGEMENT_PAGE_SIZE = 20

# Registry of the four exam-linked resource sections managed inside the
# workspace. Each entry maps a URL slug to its model, form and public labels so
# the shared list/create/edit/detail/delete views can serve all of them.
RESOURCE_SECTIONS = {
    "answer-sheets": {
        "key": "answer-sheets",
        "model": AnswerSheet,
        "form": AnswerSheetForm,
        "label": "Answer Sheet",
        "eyebrow": "ANSWER SHEETS",
        "singular": "answer sheet",
        "description": (
            "Publish answer-sheet PDFs with their related exam. Published answer "
            "sheets appear on the public Answer Sheet page with working PDF links."
        ),
        "public_view": "accounts:answer_sheets",
        "add_label": "Add answer sheet",
        "warning": "The answer sheet and its uploaded PDF will be removed from the public website.",
    },
    "registration-forms": {
        "key": "registration-forms",
        "model": RegistrationResource,
        "form": RegistrationResourceForm,
        "label": "Registration Form",
        "eyebrow": "REGISTRATION FORMS",
        "singular": "registration resource",
        "description": (
            "Publish application resources: a downloadable PDF, an official "
            "application link, or both. A resource needs at least one of the two."
        ),
        "public_view": "accounts:registration_forms",
        "add_label": "Add registration form",
        "warning": "The registration resource and its uploaded PDF will be removed from the public website.",
    },
    "previous-papers": {
        "key": "previous-papers",
        "model": PreviousPaper,
        "form": PreviousPaperForm,
        "label": "Previous Paper",
        "eyebrow": "PREVIOUS PAPERS",
        "singular": "previous paper",
        "description": (
            "Publish previous-year question papers with a required PDF. Uploaded "
            "papers are downloadable from the public Previous Paper page."
        ),
        "public_view": "accounts:previous_papers",
        "add_label": "Add previous paper",
        "warning": "The previous paper and its uploaded PDF will be removed from the public website.",
    },
    "results": {
        "key": "results",
        "model": Result,
        "form": ResultForm,
        "label": "Result",
        "eyebrow": "EXAM RESULTS",
        "singular": "result",
        "description": (
            "Publish result announcements with an official result URL and an "
            "optional PDF. A result needs at least one of the two so visitors "
            "always have a working “View Result” action."
        ),
        "public_view": "accounts:results",
        "add_label": "Add result",
        "warning": "The result announcement and its uploaded PDF will be removed from the public website.",
    },
}


def _resource_config(section):
    config = RESOURCE_SECTIONS.get(section)
    if config is None:
        raise Http404("Unknown resource section.")
    return config


def _resource_queryset(config):
    model = config["model"]
    return model.objects.select_related("exam").order_by("sort_order", "-created_at")


def _get_resource_urls_formset(instance, post_data=None):
    """Get a formset for ResourceURLs attached to a resource instance."""
    ResourceURLFormSet = formset_factory(ResourceURLForm, extra=1, can_delete=True)

    if post_data:
        formset = ResourceURLFormSet(post_data, prefix="resource_urls")
    else:
        # Initialize with existing URLs
        initial_data = []
        if instance and instance.pk:
            for url in instance.resource_urls:
                initial_data.append({
                    "label": url.label,
                    "url": url.url,
                    "target": url.target,
                    "sort_order": url.sort_order,
                    "is_active": url.is_active,
                })
        formset = ResourceURLFormSet(initial=initial_data, prefix="resource_urls")

    return formset


def _save_resource_urls(instance, formset):
    """Save ResourceURLs from a formset to a resource instance."""
    content_type = ContentType.objects.get_for_model(instance.__class__)

    # Delete all existing URLs for this instance
    ResourceURL.objects.filter(
        content_type=content_type,
        object_id=instance.pk,
    ).delete()

    # Create new URLs from formset
    for form in formset:
        if form.cleaned_data and not form.cleaned_data.get("DELETE"):
            ResourceURL.objects.create(
                content_type=content_type,
                object_id=instance.pk,
                label=form.cleaned_data["label"],
                url=form.cleaned_data["url"],
                target=form.cleaned_data["target"],
                sort_order=form.cleaned_data["sort_order"],
                is_active=form.cleaned_data["is_active"],
            )


@staff_required
def resource_list(request, section):
    config = _resource_config(section)
    model = config["model"]
    items = _resource_queryset(config)
    query = request.GET.get("q", "").strip()[:120]
    status = request.GET.get("status", "").strip()
    if query:
        items = items.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(exam__title__icontains=query)
        )
    valid_statuses = {choice for choice, _label in model.Status.choices}
    if status not in valid_statuses:
        status = ""
    else:
        items = items.filter(status=status)
    total_count = items.count()
    page = Paginator(items, RESOURCE_MANAGEMENT_PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    return render(
        request,
        "site_management/resource_list.html",
        {
            "config": config,
            "section": section,
            "page_obj": page,
            "query": query,
            "status": status,
            "status_choices": model.Status.choices,
            "total_count": total_count,
        },
    )


@staff_required
def resource_create(request, section):
    config = _resource_config(section)
    form = config["form"](request.POST or None, request.FILES or None)
    url_formset = None

    if request.method == "POST":
        url_formset = _get_resource_urls_formset(None, request.POST)
        if form.is_valid() and url_formset.is_valid():
            with transaction.atomic():
                obj = form.save()
                _save_resource_urls(obj, url_formset)
                messages.success(request, f'"{obj.title}" {config["singular"]} created.')
                return redirect(
                    "site_management:resource_detail", section=section, pk=obj.pk
                )
    else:
        # GET request - empty formset
        url_formset = _get_resource_urls_formset(None)

    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "url_formset": url_formset,
            "page_title": config["add_label"],
            "back_url": reverse("site_management:resource_list", args=[section]),
            "submit_label": f'Create {config["singular"]}',
            "form_description": config["description"],
        },
    )


@staff_required
def resource_detail(request, section, pk):
    config = _resource_config(section)
    obj = get_object_or_404(_resource_queryset(config), pk=pk)
    public_url = ""
    if obj.is_published:
        public_url = reverse(config["public_view"])
    return render(
        request,
        "site_management/resource_detail.html",
        {
            "config": config,
            "section": section,
            "object": obj,
            "public_url": public_url,
        },
    )


@staff_required
def resource_edit(request, section, pk):
    config = _resource_config(section)
    obj = get_object_or_404(config["model"], pk=pk)
    form = config["form"](request.POST or None, request.FILES or None, instance=obj)
    url_formset = None

    if request.method == "POST":
        url_formset = _get_resource_urls_formset(obj, request.POST)
        if form.is_valid() and url_formset.is_valid():
            with transaction.atomic():
                current_file = obj.pdf_file
                saved = form.save(commit=False)
                if obj.pdf_file and not form.cleaned_data.get("pdf_file"):
                    saved.pdf_file = current_file
                saved.save()
                form.save_m2m()
                _save_resource_urls(saved, url_formset)
            messages.success(request, f'"{saved.title}" {config["singular"]} updated.')
            return redirect("site_management:resource_list", section=section)
    else:
        # GET request - load existing URLs
        url_formset = _get_resource_urls_formset(obj)

    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "url_formset": url_formset,
            "page_title": f'Edit {config["singular"]}: {obj.title}',
            "back_url": reverse("site_management:resource_list", args=[section]),
            "submit_label": f'Save {config["singular"]}',
            "public_url": (
                reverse(config["public_view"]) if obj.is_published else ""
            ),
            "form_description": f'Leave the PDF file empty to keep the current file. {config["description"]}',
        },
    )


@staff_required
def resource_delete(request, section, pk):
    config = _resource_config(section)
    obj = get_object_or_404(config["model"], pk=pk)
    if request.method == "POST":
        title = obj.title
        with transaction.atomic():
            obj.delete()
        messages.success(request, f'"{title}" {config["singular"]} deleted.')
        return redirect("site_management:resource_list", section=section)
    return render(
        request,
        "site_management/confirm_delete.html",
        {
            "object_label": obj.title,
            "back_url": reverse("site_management:resource_list", args=[section]),
            "warning": config["warning"],
        },
    )


@staff_required
@require_POST
def resource_toggle(request, section, pk):
    """Publish or unpublish a resource without deleting it."""
    config = _resource_config(section)
    obj = get_object_or_404(config["model"], pk=pk)
    model = config["model"]
    if obj.status == model.Status.PUBLISHED:
        obj.status = model.Status.DRAFT
        message = f'"{obj.title}" unpublished.'
    else:
        obj.status = model.Status.PUBLISHED
        message = f'"{obj.title}" published.'
    with transaction.atomic():
        obj.save(update_fields=["status", "updated_at"])
    messages.success(request, message)
    return redirect("site_management:resource_list", section=section)


@staff_required
def social_profiles(request):
    profiles = list(SocialMediaProfile.objects.all())
    configured_platforms = {profile.platform for profile in profiles}
    missing_platforms = [
        platform
        for platform, _label in SocialMediaProfile.Platform.choices
        if platform not in configured_platforms
    ]
    profiles.extend(
        SimpleNamespace(
            pk=None,
            platform=platform,
            **defaults,
        )
        for platform, defaults in DEFAULT_SOCIAL_PROFILE_SETTINGS.items()
        if platform not in configured_platforms
    )
    profiles.sort(key=lambda profile: (profile.display_order, profile.platform))
    return render(
        request,
        "site_management/social_profiles.html",
        {"profiles": profiles, "missing_platforms": missing_platforms},
    )


@staff_required
def social_profile_create(request):
    initial = {}
    platform = request.GET.get("platform", "")
    if (
        request.method == "GET"
        and platform in DEFAULT_SOCIAL_PROFILE_SETTINGS
        and not SocialMediaProfile.objects.filter(platform=platform).exists()
    ):
        initial = {
            "platform": platform,
            **DEFAULT_SOCIAL_PROFILE_SETTINGS[platform],
        }
    form = SocialMediaProfileForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            profile = form.save()
        messages.success(request, f"{profile.get_platform_display()} profile saved.")
        return redirect("site_management:social_profiles")
    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "page_title": "Add a social profile",
            "back_url": reverse("site_management:social_profiles"),
            "submit_label": "Save profile",
            "form_description": "Public location: the selected header/footer placement on every public page. One profile may be configured per supported platform.",
        },
    )


@staff_required
def social_profile_edit(request, profile_id):
    profile = get_object_or_404(SocialMediaProfile, pk=profile_id)
    form = SocialMediaProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            profile = form.save()
        messages.success(request, f"{profile.get_platform_display()} profile updated.")
        return redirect("site_management:social_profiles")
    return render(
        request,
        "site_management/form.html",
        {
            "form": form,
            "page_title": f"Edit {profile.get_platform_display()} profile",
            "back_url": reverse("site_management:social_profiles"),
            "submit_label": "Save profile",
            "form_description": "Public location: the selected header/footer placement on every public page.",
        },
    )


@staff_required
def social_profile_delete(request, profile_id):
    profile = get_object_or_404(SocialMediaProfile, pk=profile_id)
    if request.method == "POST":
        platform = profile.get_platform_display()
        with transaction.atomic():
            profile.delete()
        messages.success(request, f"{platform} profile removed.")
        return redirect("site_management:social_profiles")
    return render(
        request,
        "site_management/confirm_delete.html",
        {
            "object_label": profile.get_platform_display(),
            "back_url": reverse("site_management:social_profiles"),
            "warning": "This removes only the selected social profile from the public header/footer.",
        },
    )


@staff_required
def comment_moderation(request):
    """Staff review board for community comments."""
    if not (
        request.user.has_perm("comments.view_comment")
        or request.user.has_perm("comments.change_comment")
        or request.user.is_superuser
    ):
        raise PermissionDenied("You do not have permission to view community comments.")

    status_filter = request.GET.get("status", "pending")
    comments_qs = Comment.objects.all().select_related("author").order_by("-created_at")

    total_count = comments_qs.count()
    pending_count = Comment.objects.filter(status=Comment.Status.PENDING).count()
    published_count = Comment.objects.filter(status=Comment.Status.PUBLISHED).count()
    rejected_count = Comment.objects.filter(status=Comment.Status.REJECTED).count()

    if status_filter in dict(Comment.Status.choices):
        comments_qs = comments_qs.filter(status=status_filter)

    paginator = Paginator(comments_qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    can_moderate = (
        request.user.has_perm("comments.change_comment")
        or request.user.is_superuser
    )
    can_delete = (
        request.user.has_perm("comments.delete_comment")
        or request.user.is_superuser
    )

    return render(
        request,
        "site_management/comment_moderation.html",
        {
            "page_obj": page_obj,
            "status_filter": status_filter,
            "total_count": total_count,
            "pending_count": pending_count,
            "published_count": published_count,
            "rejected_count": rejected_count,
            "can_moderate": can_moderate,
            "can_delete": can_delete,
        },
    )


@staff_required
@require_POST
def comment_action(request, comment_id, action):
    """Approve, reject, or delete a community comment."""
    comment = get_object_or_404(Comment, pk=comment_id)
    return_status = request.GET.get("status", "pending")

    if action in {"publish", "reject"}:
        if not (
            request.user.has_perm("comments.change_comment")
            or request.user.is_superuser
        ):
            raise PermissionDenied("You do not have permission to moderate comments.")
        if action == "publish":
            comment.status = Comment.Status.PUBLISHED
            comment.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Comment #{comment.pk} by {comment.author} approved and published.")
        elif action == "reject":
            comment.status = Comment.Status.REJECTED
            comment.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Comment #{comment.pk} by {comment.author} marked as rejected.")
    elif action == "delete":
        if not (
            request.user.has_perm("comments.delete_comment")
            or request.user.is_superuser
        ):
            raise PermissionDenied("You do not have permission to delete comments.")
        comment.delete()
        messages.success(request, f"Comment #{comment_id} was permanently deleted.")
    else:
        raise Http404("Invalid comment action.")

    redirect_url = reverse("site_management:comment_moderation")
    if return_status:
        redirect_url += f"?status={return_status}"
    return redirect(redirect_url)


@staff_required
def ai_status(request):
    """Read-only diagnostics and daily request metrics for the AI Assistant."""
    provider = getattr(settings, "AI_PROVIDER", "gemini")
    normalized_provider = provider.strip().lower() if isinstance(provider, str) else "gemini"
    if normalized_provider == "openrouter":
        model_name = getattr(settings, "OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b-20260604")
        raw_key = getattr(settings, "OPENROUTER_API_KEY", "")
        placeholder = getattr(settings, "OPENROUTER_PLACEHOLDER_KEY", "PASTE_YOUR_OPENROUTER_API_KEY_HERE")
    else:
        model_name = getattr(settings, "GEMINI_MODEL", "gemini-3.8-flash")
        raw_key = getattr(settings, "GEMINI_API_KEY", "")
        placeholder = getattr(settings, "GEMINI_PLACEHOLDER_KEY", "PASTE_YOUR_GEMINI_API_KEY_HERE")
    enabled = bool(getattr(settings, "AI_ENABLED", False))
    rate_limit = getattr(settings, "AI_RATE_LIMIT_PER_MINUTE", 15)
    has_api_key = bool(raw_key and raw_key != placeholder)

    today = timezone.localdate()
    today_stats = AIDailyUsage.objects.filter(usage_date=today).aggregate(
        total_requests=Sum("request_count"),
        total_users=Count("id"),
    )
    today_requests = today_stats["total_requests"] or 0
    today_users = today_stats["total_users"] or 0

    week_ago = today - timedelta(days=7)
    recent_usage = list(
        AIDailyUsage.objects.filter(usage_date__gte=week_ago)
        .values("usage_date")
        .annotate(requests=Sum("request_count"), users=Count("user"))
        .order_by("-usage_date")
    )

    return render(
        request,
        "site_management/ai_status.html",
        {
            "provider": provider,
            "model_name": model_name,
            "enabled": enabled,
            "rate_limit": rate_limit,
            "has_api_key": has_api_key,
            "today_requests": today_requests,
            "today_users": today_users,
            "recent_usage": recent_usage,
        },
    )


# ---------------------------------------------------------------------------
# Users management (inside the custom workspace, not Django Admin)
# ---------------------------------------------------------------------------

UserModel = get_user_model()

ACCOUNTS_VIEW_PERM = "accounts.view_emailuser"
ACCOUNTS_CHANGE_PERM = "accounts.change_emailuser"


def _can_view_accounts(user):
    return bool(
        user.is_superuser
        or user.has_perm(ACCOUNTS_VIEW_PERM)
        or user.has_perm(ACCOUNTS_CHANGE_PERM)
    )


def _can_change_accounts(user):
    return bool(user.is_superuser or user.has_perm(ACCOUNTS_CHANGE_PERM))


def _can_manage_account(actor, target):
    """A non-superuser may never modify a superuser's account."""
    return not (target.is_superuser and not actor.is_superuser)


@staff_required
def user_list(request):
    """Searchable, paginated list of accounts that can sign in to the website."""
    if not _can_view_accounts(request.user):
        raise PermissionDenied("You do not have permission to view user accounts.")

    query = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    status_filter = request.GET.get("status", "")

    accounts = UserModel.objects.all().order_by("-date_joined", "-pk")
    if query:
        accounts = accounts.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(full_name__icontains=query)
        )
    if role == "staff":
        accounts = accounts.filter(is_staff=True)
    elif role == "member":
        accounts = accounts.filter(is_staff=False)
    if status_filter == "active":
        accounts = accounts.filter(is_active=True)
    elif status_filter == "inactive":
        accounts = accounts.filter(is_active=False)

    total_accounts = UserModel.objects.count()
    staff_accounts = UserModel.objects.filter(is_staff=True).count()
    active_accounts = UserModel.objects.filter(is_active=True).count()

    page_obj = Paginator(accounts, 25).get_page(request.GET.get("page"))

    return render(
        request,
        "site_management/user_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "role": role,
            "status_filter": status_filter,
            "total_accounts": total_accounts,
            "staff_accounts": staff_accounts,
            "active_accounts": active_accounts,
            "inactive_accounts": total_accounts - active_accounts,
            "can_manage": _can_change_accounts(request.user),
        },
    )


@staff_required
def user_detail(request, user_id):
    """Read an account and edit its safe profile fields (never the password)."""
    if not _can_view_accounts(request.user):
        raise PermissionDenied("You do not have permission to view user accounts.")

    account = get_object_or_404(UserModel, pk=user_id)
    is_self = account.pk == request.user.pk
    can_manage = _can_change_accounts(request.user) and _can_manage_account(
        request.user, account
    )

    form = ManagementUserEditForm(request.POST or None, instance=account)
    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied("You do not have permission to edit this account.")
        if form.is_valid():
            with transaction.atomic():
                form.save()
            messages.success(request, f'"{account.username}" account details updated.')
            return redirect("site_management:user_detail", user_id=account.pk)

    return render(
        request,
        "site_management/user_detail.html",
        {
            "account": account,
            "form": form,
            "can_manage": can_manage,
            "can_change_access": can_manage and not is_self,
            "is_self": is_self,
        },
    )


@staff_required
@require_POST
def user_action(request, user_id, action):
    """Activate/deactivate an account or grant/revoke staff access."""
    if not _can_change_accounts(request.user):
        raise PermissionDenied("You do not have permission to manage user accounts.")

    account = get_object_or_404(UserModel, pk=user_id)
    if not _can_manage_account(request.user, account):
        raise PermissionDenied("Only a superuser can manage another superuser account.")
    if account.pk == request.user.pk:
        raise PermissionDenied("You cannot change your own account access from here.")

    if action == "activate":
        account.is_active = True
        account.save(update_fields=["is_active"])
        messages.success(request, f'"{account.username}" can sign in again.')
    elif action == "deactivate":
        account.is_active = False
        account.save(update_fields=["is_active"])
        messages.success(request, f'"{account.username}" can no longer sign in.')
    elif action == "grant-staff":
        account.is_staff = True
        account.save(update_fields=["is_staff"])
        messages.success(
            request, f'"{account.username}" now has staff access to this workspace.'
        )
    elif action == "revoke-staff":
        account.is_staff = False
        account.save(update_fields=["is_staff"])
        messages.success(
            request, f'"{account.username}" no longer has staff access to this workspace.'
        )
    else:
        raise Http404("Unknown user action.")

    return redirect("site_management:user_detail", user_id=account.pk)
