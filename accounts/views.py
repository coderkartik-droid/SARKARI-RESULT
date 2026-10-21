import re
from types import SimpleNamespace
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    PasswordResetConfirmView,
    PasswordResetCompleteView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.text import slugify
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import ProfileForm, SignupForm
from .login_throttle import clear_failures, is_locked, record_failure
from .models import EmailUser
from site_management.forms import ContactMessageForm
from site_management.models import (
    AnswerSheet,
    ContentItem,
    ContentLink,
    ContentSection,
    DEFAULT_SOCIAL_PROFILE_SETTINGS,
    Exam,
    ExamLink,
    ExamPDF,
    PreviousPaper,
    RegistrationResource,
    Result,
    SocialMediaProfile,
    WebsiteSettings,
    WebsitePage,
)


GENERIC_LOGIN_ERROR = "Invalid username or email, or password."
HOMEPAGE_ITEM_LIMIT = 2
HOMEPAGE_EXAM_LIMIT = 4
SECTION_PAGE_SIZE = 20
FOOTER_INFO_PAGE_ROUTES = (
    (WebsitePage.PageType.ABOUT_US, "About Us", "about_us"),
    (WebsitePage.PageType.CONTACT_US, "Contact", "contact_us"),
    (WebsitePage.PageType.PRIVACY_POLICY, "Privacy Policy", "privacy_policy"),
    (WebsitePage.PageType.TERMS_AND_CONDITIONS, "Terms & Conditions", "terms_and_conditions"),
    (WebsitePage.PageType.DISCLAIMER, "Disclaimer", "disclaimer"),
)
WEBSITE_PAGE_ROUTE_NAMES = (
    (WebsitePage.PageType.ABOUT_US, "about_us"),
    (WebsitePage.PageType.CONTACT_US, "contact_us"),
    (WebsitePage.PageType.PRIVACY_POLICY, "privacy_policy"),
    (WebsitePage.PageType.TERMS_AND_CONDITIONS, "terms_and_conditions"),
    (WebsitePage.PageType.DISCLAIMER, "disclaimer"),
    (WebsitePage.PageType.CONTENT_DETAILS, "content_details"),
)
SAFE_BLOCK_VALUES = {
    "standard", "notice", "feature", "callout", "card", "compact",
    "small", "medium", "large", "contain", "cover", "top-left",
    "top-right", "left", "right", "background", "center", "normal",
    "relaxed", "violet", "blue", "cyan", "green", "amber", "rose",
}


def _content_presentation(item):
    classes = []
    for value, prefix in (
        (item.block_type, "portal-type--"),
        (item.layout, "portal-layout--"),
        (item.image_position, "portal-image-position--"),
        (getattr(item, "image_alignment", ""), "portal-image-align--"),
        (item.image_size, "portal-image-size--"),
        (item.image_fit, "portal-image-fit--"),
        (item.content_alignment, "portal-align--"),
        (item.border_radius, "portal-radius--"),
        (item.spacing, "portal-spacing--"),
        (item.badge_color, "portal-badge--"),
    ):
        if value in SAFE_BLOCK_VALUES:
            classes.append(f"{prefix}{value}")
    if item.is_featured:
        classes.append("portal-featured")
    if item.custom_css_class and re.fullmatch(
        r"[A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z][A-Za-z0-9_-]*)*",
        item.custom_css_class,
    ):
        classes.append(item.custom_css_class)

    style_rules = []
    for property_name, value in (
        ("background-color", item.background_color),
        ("color", item.text_color),
        ("border-color", item.border_color),
    ):
        if value and re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            style_rules.append(f"{property_name}:{value}")
    return " ".join(classes), ";".join(style_rules)


def _safe_color_style(color, background):
    declarations = []
    if color and re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        declarations.append(f"color:{color}")
    if background and re.fullmatch(r"#[0-9A-Fa-f]{6}", background):
        declarations.extend((f"background-color:{background}", "display:inline-block", "padding:.12em .32em"))
    return ";".join(declarations)


def _icon_color_style(color):
    return f"color:{color}" if color and re.fullmatch(r"#[0-9A-Fa-f]{6}", color) else ""


def _attach_link_icon_styles(sections):
    for section in sections:
        for item in section.items.all():
            for linked_item in (item, *item.children.all()):
                for link in linked_item.links.all():
                    link.icon_style = _icon_color_style(link.icon_color)


def _scheduled_content_items(queryset, *, homepage=False):
    current_time = timezone.now()
    queryset = queryset.filter(is_active=True).filter(
        Q(publish_at__isnull=True) | Q(publish_at__lte=current_time)
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=current_time)
    )
    if homepage:
        queryset = queryset.filter(show_on_homepage=True)
    return queryset


def _displayable_content_items(queryset):
    return queryset.filter(
        Q(label__gt="")
        | Q(body__gt="")
        | Q(subtitle__gt="")
        | Q(short_description__gt="")
        | Q(additional_description__gt="")
        | Q(badge_text__gt="")
        | Q(eyebrow_text__gt="")
        | Q(highlight_text__gt="")
        | Q(image__gt="")
        | Q(thumbnail_image__gt="")
        | Q(secondary_image__gt="")
        | Q(button_text__gt="", button_url__gt="")
        | Q(primary_link_text__gt="", url__gt="")
        | Q(secondary_link_text__gt="", secondary_link_url__gt="")
    )


def _public_not_found(request):
    return render(
        request,
        "accounts/page_unavailable.html",
        {
            "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
            "navigation_sections": _public_navigation_sections(),
            **_public_footer_context(),
        },
        status=404,
    )


def _visible_content_links(item):
    if item is None or not hasattr(item, "links"):
        return []
    current_time = timezone.now()
    prefetched = getattr(item, "_prefetched_objects_cache", {}).get("links")
    if prefetched is not None:
        links = [
            link for link in prefetched
            if link.is_active
            and (link.starts_at is None or link.starts_at <= current_time)
            and (link.ends_at is None or link.ends_at > current_time)
        ]
    else:
        links = list(
            item.links.filter(is_active=True)
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=current_time))
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=current_time))
            .order_by("display_order", "pk")
        )
    for link in links:
        link.icon_style = _icon_color_style(link.icon_color)
    return links


def _scheduled_content_links():
    current_time = timezone.now()
    return ContentLink.objects.filter(is_active=True).filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=current_time)
    ).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=current_time)
    ).order_by("display_order", "pk")


def _category_listing_url(label, configured_url, available_slugs):
    category_aliases = {
        "results": "results",
        "latest results": "results",
        "previous paper": "previous-papers",
        "previous papers": "previous-papers",
        "previous year papers": "previous-papers",
    }
    category = category_aliases.get(label.strip().casefold())
    if category is None:
        category = slugify(label)
    if category not in available_slugs:
        fragment = urlsplit(configured_url).fragment
        category = category_aliases.get(fragment.replace("-", " ").removesuffix(" items"))
        if category is None:
            category = fragment.removesuffix("-items")
    if category in available_slugs:
        return reverse("accounts:section_list", args=[category])
    # Handle special anchor aliases for static pages
    if configured_url in {"#contact", "#contact-us", "#tools"}:
        return reverse("contact_us") if configured_url.startswith("#contact") else reverse("tools")
    if configured_url in {"#about", "#about-us"}:
        return reverse("about_us")
    return ""


def _attach_category_listing_urls(sections, available_slugs):
    for section in sections:
        for item in section.items.all():
            item.listing_url = _category_listing_url(
                item.label,
                item.url,
                available_slugs,
            )
            for child in item.children.all():
                child.listing_url = _category_listing_url(
                    child.label,
                    child.url,
                    available_slugs,
                )


def _auth_page(request, mode="login", **context):
    return render(
        request,
        "index.html",
        {
            "mode": mode,
            "signup_form": context.pop("signup_form", SignupForm()),
            "login_identifier": context.pop("login_identifier", ""),
            "next": context.pop("next", ""),
            # .env injection point: GOOGLE_OAUTH_CLIENT_ID comes from
            # GOOGLE_CLIENT_ID in the root .env (see config/settings/base.py).
            "google_client_id": getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", ""),
            "google_client_configured": is_google_oauth_configured(),
            "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
            "navigation_sections": _public_navigation_sections(),
            **_public_footer_context(),
            **context,
        },
    )


def _public_navigation_sections():
    """CMS navigation sections rendered in public chrome.

    The public header menu is now a fixed nine-section allowlist rendered
    directly in ``base_public.html``, so CMS navigation sections are no longer
    injected there. This helper is kept because many views still pass the
    context variable; it returns an empty list so no extra public menu items
    can appear.
    """
    return []


def _dashboard_url(user):
    if user.is_superuser:
        return reverse("site_management:dashboard")
    return reverse("accounts:dashboard")


def _login_redirect_url(request, user):
    fallback_url = _dashboard_url(user)
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if not next_url or not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return fallback_url

    next_path = urlsplit(next_url).path
    cms_path = reverse("site_management:dashboard")
    user_dashboard_path = reverse("accounts:dashboard")
    management_login_path = reverse("site_management:login")
    if user.is_superuser and next_path in {
        user_dashboard_path,
        management_login_path,
    }:
        return fallback_url
    if not (user.is_staff or user.is_superuser) and next_path.startswith(cms_path):
        return fallback_url
    return next_url


def _public_footer_links(footer_sections):
    _attach_link_icon_styles(footer_sections)
    # The public navigation is fixed to the nine-section allowlist, so the
    # footer no longer advertises CMS homepage categories. footer_categories
    # remains for backwards compatibility but stays empty.
    footer_categories = []
    published_page_types = set(
        WebsitePage.objects.filter(
            page_type__in=[page_type for page_type, _ in WEBSITE_PAGE_ROUTE_NAMES],
            is_published=True,
        ).values_list("page_type", flat=True)
    )
    unpublished_page_paths = {
        reverse(route_name)
        for page_type, route_name in WEBSITE_PAGE_ROUTE_NAMES
        if page_type not in published_page_types
    }
    generated_page_paths = {
        reverse(route_name)
        for _, route_name in WEBSITE_PAGE_ROUTE_NAMES
    }
    anchor_page_paths = {
        "#about": reverse("about_us"),
        "#about-us": reverse("about_us"),
        "#contact": reverse("contact_us"),
        "#contact-us": reverse("contact_us"),
    }
    for section in footer_sections:
        for item in section.items.all():
            for footer_item in (item, *item.children.all()):
                configured_path = urlsplit(footer_item.url).path
                alias_path = anchor_page_paths.get(footer_item.url, configured_path)
                if (
                    alias_path in unpublished_page_paths
                    or configured_path in generated_page_paths
                    or (
                        footer_item.url.startswith("#")
                        and footer_item.url not in anchor_page_paths
                    )
                ):
                    footer_item.is_active = False
        section.visible_items = [
            item for item in section.items.all() if item.is_active and item.label
        ]
    always_available_footer_page_types = {
        WebsitePage.PageType.ABOUT_US,
        WebsitePage.PageType.PRIVACY_POLICY,
        WebsitePage.PageType.TERMS_AND_CONDITIONS,
        WebsitePage.PageType.DISCLAIMER,
    }
    footer_pages = [
        {"label": label, "url": reverse(route_name)}
        for page_type, label, route_name in FOOTER_INFO_PAGE_ROUTES
        if page_type in published_page_types or page_type in always_available_footer_page_types
    ]
    return {
        "footer_categories": footer_categories[:3],
        "footer_extra_categories": footer_categories[3:],
        "footer_pages": footer_pages,
    }


def _public_footer_context(footer_sections=None):
    # Footer column allowlist: only footer columns whose slug is in this set
    # are rendered publicly. Other CMS footer columns (e.g. extra category
    # lists) keep their data but are never shown on the public site.
    PUBLIC_FOOTER_SECTION_SLUGS = {"footer-information", "footer-quick-links", "footer-social", "website-pages"}
    if footer_sections is None:
        footer_sections = list(
            ContentSection.objects.filter(
                area=ContentSection.Area.FOOTER,
                is_active=True,
            ).prefetch_related(
                Prefetch("items", queryset=_public_content_items())
            )
        )
    available_slugs = set(
        ContentSection.objects.filter(
            area=ContentSection.Area.HOMEPAGE,
            is_active=True,
        ).values_list("slug", flat=True)
    )
    footer_sections = [
        section for section in footer_sections if section.slug in PUBLIC_FOOTER_SECTION_SLUGS
    ]
    _attach_category_listing_urls(footer_sections, available_slugs)
    configured_profiles = {
        profile.platform: profile
        for profile in SocialMediaProfile.objects.filter(
            platform__in=DEFAULT_SOCIAL_PROFILE_SETTINGS
        )
    }
    header_profiles = list(SocialMediaProfile.objects.filter(
        is_active=True,
        display_location__in=[SocialMediaProfile.DisplayLocation.HEADER, SocialMediaProfile.DisplayLocation.BOTH],
    ).order_by("display_order", "pk"))
    footer_profiles = list(SocialMediaProfile.objects.filter(
        is_active=True,
        display_location__in=[SocialMediaProfile.DisplayLocation.FOOTER, SocialMediaProfile.DisplayLocation.BOTH],
    ).order_by("display_order", "pk"))
    for platform, defaults in DEFAULT_SOCIAL_PROFILE_SETTINGS.items():
        if platform in configured_profiles:
            continue
        footer_profiles.append(
            SimpleNamespace(platform=platform, **defaults)
        )
    footer_profiles.sort(key=lambda profile: (profile.display_order, profile.platform))
    for profile in [*header_profiles, *footer_profiles]:
        profile.icon_style = _icon_color_style(profile.icon_color)
    return {
        "footer_sections": footer_sections,
        "header_social_profiles": header_profiles,
        "footer_social_profiles": footer_profiles,
        **_public_footer_links(footer_sections),
    }


def _active_exam_links():
    """Publicly visible exam URLs (registration, notification, …) in order."""
    return ExamLink.objects.filter(is_active=True).order_by("sort_order", "pk")


def _published_exams_queryset():
    """Publicly visible exams with their active PDFs and URLs preloaded."""
    current_time = timezone.now()
    return (
        Exam.objects.filter(status=Exam.Status.PUBLISHED, is_active=True)
        .filter(Q(publish_at__isnull=True) | Q(publish_at__lte=current_time))
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=current_time))
        .prefetch_related(
            "eligible_qualifications",
            Prefetch("links", queryset=_active_exam_links()),
            Prefetch(
                "pdfs",
                queryset=ExamPDF.objects.filter(is_active=True).order_by(
                    "sort_order", "pk"
                ),
            )
        )
        .order_by("sort_order", "-created_at")
    )


def home(request):
    query = request.GET.get("q", "").strip()[:120]
    normalized_query = query.casefold()
    website_settings = WebsiteSettings.objects.first() or WebsiteSettings()

    navigation_sections = []  # Public menu is a fixed allowlist in base_public.html
    footer_sections = list(
        ContentSection.objects.filter(
            area=ContentSection.Area.FOOTER,
            is_active=True,
        ).prefetch_related(
            Prefetch(
                "items",
                queryset=_public_content_items(),
            )
        )
    )
    available_slugs = set(
        ContentSection.objects.filter(
            area=ContentSection.Area.HOMEPAGE,
            is_active=True,
        ).values_list("slug", flat=True)
    )
    _attach_category_listing_urls(footer_sections, available_slugs)
    _attach_link_icon_styles(footer_sections)

    announcement_items = [
        item
        for section in ContentSection.objects.filter(
            area=ContentSection.Area.ANNOUNCEMENTS,
            is_active=True,
        ).prefetch_related(
            Prefetch(
                "items",
                queryset=_displayable_content_items(
                    _scheduled_content_items(
                        ContentItem.objects.filter(parent__isnull=True)
                    ).prefetch_related(
                        Prefetch("links", queryset=_scheduled_content_links())
                    )
                ),
            )
        )
        for item in section.items.all()
    ]
    hero_actions = [
        item
        for section in ContentSection.objects.filter(
            area=ContentSection.Area.HERO_ACTIONS,
            is_active=True,
        ).prefetch_related(
            Prefetch(
                "items",
                queryset=_scheduled_content_items(
                    ContentItem.objects.filter(
                        parent__isnull=True,
                        label__gt="",
                        url__gt="",
                    )
                ).prefetch_related(
                    Prefetch("links", queryset=_scheduled_content_links())
                ),
            )
        )
        for item in section.items.all()
    ]
    for item in [*announcement_items, *hero_actions]:
        item.visible_links = _visible_content_links(item)

    # Homepage data blocks. Every block is fed by the same published QuerySet
    # as its public listing page, so records saved and published in the admin
    # workspace appear on the homepage automatically.
    today = timezone.localdate()
    published_exams = _published_exams_queryset()
    exam_entries = list(published_exams[:HOMEPAGE_EXAM_LIMIT])
    upcoming_exam_entries = list(
        published_exams.filter(exam_date__gte=today).order_by(
            "exam_date", "sort_order"
        )[:HOMEPAGE_EXAM_LIMIT]
    )
    recent_exam_entries = list(
        published_exams.filter(exam_date__lt=today).order_by(
            "-exam_date", "sort_order"
        )[:HOMEPAGE_EXAM_LIMIT]
    )

    # Homepage blocks for the exam-linked resource sections (Answer Sheet,
    # Registration Form, Previous Paper, Result). RESOURCE_PUBLIC_SECTIONS
    # supplies the model, public labels and list/detail route names.
    resource_blocks = []
    for section_key, config in RESOURCE_PUBLIC_SECTIONS.items():
        items = list(
            _published_resource_queryset(config["model"])[:HOMEPAGE_ITEM_LIMIT]
        )
        for item in items:
            item.detail_url = reverse(config["detail_name"], args=[item.pk])
        resource_blocks.append(
            {
                "id": section_key,
                "kicker": config["kicker"],
                "title": config["title"],
                "intro": config["intro"],
                "icon": config["icon"],
                "kind": config["kind"],
                "list_url": reverse(config["list_name"]),
                "items": items,
                "empty_message": config["empty_message"],
            }
        )

    if query:

        def _matches(exam):
            return normalized_query in f"{exam.title} {exam.description}".casefold()

        exam_entries = [exam for exam in exam_entries if _matches(exam)]
        recent_exam_entries = [exam for exam in recent_exam_entries if _matches(exam)]
        upcoming_exam_entries = [
            exam for exam in upcoming_exam_entries if _matches(exam)
        ]
        for block in resource_blocks:
            block["items"] = [
                item
                for item in block["items"]
                if normalized_query
                in (
                    f"{item.title} {item.description} "
                    f"{item.exam.title if item.exam_id else ''}".casefold()
                )
            ]

    for exam in [*exam_entries, *recent_exam_entries, *upcoming_exam_entries]:
        exam.detail_url = reverse("accounts:exam_detail", args=[exam.pk])

    total_matches = (
        len(exam_entries)
        + len(recent_exam_entries)
        + len(upcoming_exam_entries)
        + sum(len(block["items"]) for block in resource_blocks)
    )

    exam_blocks = [
        {
            "id": "exams",
            "kicker": "EXAMS",
            "title": "Exams",
            "intro": "Latest exam announcements with official notifications and download links.",
            "list_url": reverse("accounts:exams"),
            "items": exam_entries,
            "empty_message": "There are no published exams yet.",
        },
        {
            "id": "recent-exams",
            "kicker": "RECENT EXAMS",
            "title": "Recent Exams",
            "intro": "Recently concluded exams with their official notifications and download links.",
            "list_url": reverse("accounts:recent_exams"),
            "items": recent_exam_entries,
            "empty_message": "There are no recent exams right now.",
        },
        {
            "id": "upcoming-exams",
            "kicker": "UPCOMING EXAMS",
            "title": "Upcoming Exams",
            "intro": "Exam announcements with an exam date that is today or later.",
            "list_url": reverse("accounts:upcoming_exams"),
            "items": upcoming_exam_entries,
            "empty_message": "There are no upcoming exams right now.",
        },
    ]

    return render(
        request,
        "accounts/home.html",
        {
            "exam_blocks": exam_blocks,
            "resource_blocks": resource_blocks,
            "query": query,
            "result_count": total_matches,
            "has_homepage_content": total_matches > 0,
            "navigation_sections": navigation_sections,
            "footer_sections": footer_sections,
            "website_settings": website_settings,
            **_public_footer_context(footer_sections),
            "announcement_items": announcement_items,
            "hero_actions": hero_actions,
        },
    )


def section_list(request, slug):
    # Public section allowlist: only these homepage CMS sections get public
    # listing pages. Unrelated sections keep their data but are not routed.
    PUBLIC_HOMEPAGE_SECTION_SLUGS = {"previous-papers", "results"}
    section = ContentSection.objects.filter(
        area=ContentSection.Area.HOMEPAGE,
        is_active=True,
        slug=slug,
        slug__in=PUBLIC_HOMEPAGE_SECTION_SLUGS,
    ).first()
    if section is None:
        return _public_not_found(request)
    items = _displayable_content_items(
        _scheduled_content_items(
            ContentItem.objects.filter(
                section=section,
                parent__isnull=True,
            )
        )
    ).order_by("-created_at", "-pk")
    query = request.GET.get("q", "").strip()[:120]
    if query:
        items = items.filter(
            Q(label__icontains=query)
            | Q(subtitle__icontains=query)
            | Q(short_description__icontains=query)
            | Q(body__icontains=query)
        )
    page = Paginator(items, SECTION_PAGE_SIZE).get_page(request.GET.get("page"))
    for item in page.object_list:
        item.block_classes, item.block_style = _content_presentation(item)
        item.title_style = _safe_color_style(
            item.title_color, item.title_background_color
        )
        item.subtitle_style = _safe_color_style(
            item.subtitle_color, item.subtitle_background_color
        )
        item.visible_links = _visible_content_links(item)
    return render(
        request,
        "accounts/section_list.html",
        {
            "section": section,
            "page_obj": page,
            "query": query,
            "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
            "navigation_sections": _public_navigation_sections(),
            **_public_footer_context(),
        },
    )


def section_item_detail(request, slug, item_id):
    item = _displayable_content_items(
        _scheduled_content_items(ContentItem.objects.select_related("section"))
    ).filter(
        pk=item_id,
        section__slug=slug,
        section__area=ContentSection.Area.HOMEPAGE,
        section__is_active=True,
        parent__isnull=True,
    ).first()
    if item is None:
        return _public_not_found(request)
    item.visible_links = _visible_content_links(item)
    return render(
        request,
        "accounts/content_item_detail.html",
        {
            "section": item.section,
            "item": item,
            "block_classes": _content_presentation(item)[0],
            "block_style": _content_presentation(item)[1],
            "title_style": _safe_color_style(
                item.title_color, item.title_background_color
            ),
            "subtitle_style": _safe_color_style(
                item.subtitle_color, item.subtitle_background_color
            ),
            "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
            "navigation_sections": _public_navigation_sections(),
            **_public_footer_context(),
        },
    )


def _public_content_items():
    children = _scheduled_content_items(ContentItem.objects.all()).prefetch_related(
        Prefetch("links", queryset=_scheduled_content_links())
    )
    return _scheduled_content_items(ContentItem.objects.filter(
        parent__isnull=True,
    )).prefetch_related(
        Prefetch("children", queryset=children),
        Prefetch("links", queryset=_scheduled_content_links()),
    )


def _tools_context(include_landing=False):
    context = {
        "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
        "navigation_sections": _public_navigation_sections(),
        **_public_footer_context(),
    }
    if include_landing:
        tools_section = ContentSection.objects.filter(
            area=ContentSection.Area.TOOLS,
            is_active=True,
        ).first()
        tool_paths = {
            reverse("tools_image_resizer"),
            reverse("tools_jpg_to_pdf"),
            reverse("tools_photo_name_date"),
            reverse("tools_photo_signature_joiner"),
            reverse("tools_resume_cv_photo"),
        }
        tool_cards = []
        tools_has_items = False
        if tools_section:
            tools_has_items = tools_section.items.exists()
            items = _scheduled_content_items(
                ContentItem.objects.filter(
                    section=tools_section,
                    parent__isnull=True,
                    url__in=tool_paths,
                )
            ).order_by("sort_order", "pk")
            for item in items:
                item.tool_url = item.url
                tool_cards.append(item)
        context.update({
            "tools_section": tools_section,
            "tools_cards": tool_cards,
            "tools_has_items": tools_has_items,
        })
    return context


def tools(request):
    """Landing page listing the available photo utilities."""
    return render(request, "accounts/tools.html", _tools_context(include_landing=True))


def tools_image_resizer(request):
    """Client-side image resizer tool."""
    return render(request, "accounts/tools/image_resizer.html", _tools_context())


def tools_jpg_to_pdf(request):
    """Client-side JPG to PDF converter tool."""
    return render(request, "accounts/tools/jpg_to_pdf.html", _tools_context())


def tools_photo_name_date(request):
    """Client-side photo name & date maker tool."""
    return render(request, "accounts/tools/photo_name_date.html", _tools_context())


def tools_photo_signature_joiner(request):
    """Client-side photo + signature joiner tool."""
    return render(request, "accounts/tools/photo_signature_joiner.html", _tools_context())


def tools_resume_cv_photo(request):
    """Client-side resume/CV photo preparation tool."""
    return render(request, "accounts/tools/resume_cv_photo.html", _tools_context())


def exams_list(request):
    """Public listing page for exam announcements with PDF attachments."""
    exams = _published_exams_queryset()

    query = request.GET.get("q", "").strip()[:120]
    if query:
        exams = exams.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
        )

    page = Paginator(exams, 20).get_page(request.GET.get("page"))

    user = request.user
    if user.is_authenticated:
        # Server-side eligibility from the signed-in user's saved profile.
        # Missing DOB/qualification surfaces as "incomplete", never eligible.
        from jobs.eligibility import evaluate_candidate_eligibility

        for exam in page.object_list:
            exam.eligibility = evaluate_candidate_eligibility(
                exam,
                dob=getattr(user, "date_of_birth", None),
                qualification=getattr(user, "qualification", "") or None,
            )

    return render(
        request,
        "accounts/exams_list.html",
        {
            "page_obj": page,
            "query": query,
            "list_url": reverse("accounts:exams"),
            "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
            "navigation_sections": _public_navigation_sections(),
            **_public_footer_context(),
        },
    )


def exam_detail(request, pk):
    """Public detail page for a single exam announcement."""
    exam = get_object_or_404(_published_exams_queryset(), pk=pk)

    related_exams = list(_published_exams_queryset().exclude(pk=exam.pk)[:3])
    for related in related_exams:
        related.detail_url = reverse("accounts:exam_detail", args=[related.pk])

    # Server-side eligibility from the signed-in user's saved profile. A missing
    # profile or incomplete exam criteria surfaces as "incomplete", never eligible.
    exam_eligibility = None
    user = request.user
    if user.is_authenticated:
        from jobs.eligibility import evaluate_candidate_eligibility

        exam_eligibility = evaluate_candidate_eligibility(
            exam,
            dob=getattr(user, "date_of_birth", None),
            qualification=getattr(user, "qualification", "") or None,
        )

    return render(
        request,
        "accounts/exam_detail.html",
        {
            "exam": exam,
            "pdfs": list(exam.pdfs.all()),
            "exam_links": list(exam.links.all()),
            "visible_links": [],
            "related_exams": related_exams,
            "exam_eligibility": exam_eligibility,
            "exams_list_url": reverse("accounts:exams"),
            "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
            "navigation_sections": _public_navigation_sections(),
            **_public_footer_context(),
        },
    )


def upcoming_exams_list(request):
    """Public listing of exams whose exam date is today or later."""
    return _exam_date_list(
        request,
        kind="upcoming",
        page_kicker="UPCOMING EXAMS",
        page_title="Upcoming Exams",
        page_intro="Exam announcements with an exam date that is today or later.",
        empty_message="There are no upcoming exams right now.",
    )


def recent_exams_list(request):
    """Public listing of exams whose exam date is in the past."""
    return _exam_date_list(
        request,
        kind="recent",
        page_kicker="RECENT EXAMS",
        page_title="Recent Exams",
        page_intro="Exam announcements whose exam date has already passed.",
        empty_message="There are no recent exams right now.",
    )


def _exam_date_list(request, kind, page_kicker, page_title, page_intro, empty_message):
    today = timezone.localdate()
    exams = _published_exams_queryset()
    if kind == "upcoming":
        exams = exams.filter(exam_date__gte=today).order_by("exam_date", "sort_order")
    else:
        exams = exams.filter(exam_date__lt=today).order_by("-exam_date", "sort_order")

    query = request.GET.get("q", "").strip()[:120]
    if query:
        exams = exams.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
    page = Paginator(exams, SECTION_PAGE_SIZE).get_page(request.GET.get("page"))

    user = request.user
    if user.is_authenticated:
        from jobs.eligibility import evaluate_candidate_eligibility

        for exam in page.object_list:
            exam.eligibility = evaluate_candidate_eligibility(
                exam,
                dob=getattr(user, "date_of_birth", None),
                qualification=getattr(user, "qualification", "") or None,
            )

    return render(
        request,
        "accounts/exams_list.html",
        {
            "page_obj": page,
            "query": query,
            "list_url": reverse(f"accounts:{kind}_exams"),
            "page_kicker": page_kicker,
            "page_title": page_title,
            "page_intro": page_intro,
            "empty_message": empty_message,
            "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
            "navigation_sections": _public_navigation_sections(),
            **_public_footer_context(),
        },
    )


# Public listing/detail configuration for the exam-linked resource sections.
RESOURCE_PUBLIC_SECTIONS = {
    "answer-sheets": {
        "model": AnswerSheet,
        "kicker": "ANSWER SHEETS",
        "title": "Answer Sheet",
        "intro": "Published answer-sheet PDFs for recent exams.",
        "icon": "file-search",
        "kind": "answer-sheet",
        "empty_message": "There are no published answer sheets yet.",
        "list_name": "accounts:answer_sheets",
        "detail_name": "accounts:answer_sheet_detail",
    },
    "registration-forms": {
        "model": RegistrationResource,
        "kicker": "REGISTRATION FORMS",
        "title": "Registration Form",
        "intro": "Application forms, official application links and instructions for open registrations.",
        "icon": "contact",
        "kind": "registration",
        "empty_message": "There are no published registration forms yet.",
        "list_name": "accounts:registration_forms",
        "detail_name": "accounts:registration_form_detail",
    },
    "previous-papers": {
        "model": PreviousPaper,
        "kicker": "PREVIOUS PAPERS",
        "title": "Previous Paper",
        "intro": "Previous-year question papers with downloadable PDFs.",
        "icon": "paper",
        "kind": "previous-paper",
        "empty_message": "There are no published previous papers yet.",
        "list_name": "accounts:previous_papers",
        "detail_name": "accounts:previous_paper_detail",
    },
    "results": {
        "model": Result,
        "kicker": "EXAM RESULTS",
        "title": "Result",
        "intro": "Published result announcements with official links and optional PDFs.",
        "icon": "award",
        "kind": "result",
        "empty_message": "There are no published results yet.",
        "list_name": "accounts:results",
        "detail_name": "accounts:result_detail",
    },
}


def _published_resource_queryset(model):
    """Publicly visible resources: published, active and not future-dated.

    Mirrors ``PublishedExamResource.is_published`` so a resource with a future
    publication date is never exposed publicly.
    """
    today = timezone.localdate()
    return (
        model.objects.filter(status=model.Status.PUBLISHED, is_active=True)
        .filter(Q(published_date__isnull=True) | Q(published_date__lte=today))
        .select_related("exam")
        .prefetch_related(Prefetch("exam__links", queryset=_active_exam_links()))
        .order_by("sort_order", "-created_at")
    )


def resource_section_list(request, section):
    """Public listing page for an exam-linked resource section."""
    config = RESOURCE_PUBLIC_SECTIONS.get(section)
    if config is None:
        return _public_not_found(request)
    items = _published_resource_queryset(config["model"])
    query = request.GET.get("q", "").strip()[:120]
    if query:
        items = items.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(exam__title__icontains=query)
        )
    page = Paginator(items, SECTION_PAGE_SIZE).get_page(request.GET.get("page"))
    return render(
        request,
        "accounts/resource_list.html",
        {
            "config": config,
            "section": section,
            "page_obj": page,
            "query": query,
            "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
            "navigation_sections": _public_navigation_sections(),
            **_public_footer_context(),
        },
    )


def resource_section_detail(request, section, pk):
    """Public detail page for a single published resource."""
    config = RESOURCE_PUBLIC_SECTIONS.get(section)
    if config is None:
        return _public_not_found(request)
    model = config["model"]
    item = get_object_or_404(_published_resource_queryset(model), pk=pk)
    related_items = list(
        _published_resource_queryset(model).exclude(pk=item.pk)[:3]
    )
    for related in related_items:
        related.detail_url = reverse(config["detail_name"], args=[related.pk])
    return render(
        request,
        "accounts/resource_detail.html",
        {
            "config": config,
            "section": section,
            "item": item,
            "related_items": related_items,
            "list_url": reverse(config["list_name"]),
            "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
            "navigation_sections": _public_navigation_sections(),
            **_public_footer_context(),
        },
    )


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_login_redirect_url(request, request.user))
    if request.method == "GET":
        return _auth_page(request, next=request.GET.get("next", ""))
    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])

    identifier = request.POST.get("username", "").strip()
    password = request.POST.get("password", "")
    ip_address = request.META.get("REMOTE_ADDR", "unknown")

    if is_locked(identifier.casefold(), ip_address):
        return _auth_page(
            request,
            login_error=GENERIC_LOGIN_ERROR,
            login_identifier=identifier,
            next=request.POST.get("next", ""),
        )

    user = authenticate(request, username=identifier, password=password)
    if user is None:
        record_failure(identifier.casefold(), ip_address)
        return _auth_page(
            request,
            login_error=GENERIC_LOGIN_ERROR,
            login_identifier=identifier,
            next=request.POST.get("next", ""),
        )

    clear_failures(identifier.casefold(), ip_address)
    login(request, user)
    request.session.set_expiry(
        30 * 24 * 60 * 60 if request.POST.get("remember") else 0
    )

    return redirect(_login_redirect_url(request, user))


def is_google_oauth_configured():
    client_id = getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    placeholder = getattr(settings, "GOOGLE_OAUTH_PLACEHOLDER", "")
    return bool(client_id and client_secret and client_id != placeholder)


def google_login_view(request):
    if request.user.is_authenticated:
        return redirect(_login_redirect_url(request, request.user))

    if not is_google_oauth_configured():
        messages.error(
            request,
            "Google sign-in is not configured yet. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env.",
        )
        return redirect("accounts:login")

    from allauth.socialaccount.providers.google.views import oauth2_login

    return oauth2_login(request)


@require_POST
def google_auth_verify(request):
    """
    Backend verification endpoint for the Google Identity Services button.

    The browser POSTs the JWT `credential` it received from Google's
    One Tap / GIS button. This view:
      1. Verifies the token server-side (signature, audience, expiry) via
         accounts.google_utils.verify_google_id_token — NEVER trust the raw JWT.
      2. Signs the matching user in, or auto-creates one (SOCIALACCOUNT_AUTO_SIGNUP).
      3. Links an existing account only when Google reports the email as verified
         (same security rule as the allauth adapter).

    If you later want to call a separate API (e.g. a DRF endpoint) instead of
    logging in directly, this is the place to swap in that verification call.
    """
    from .google_utils import google_email_is_verified, verify_google_id_token

    def _json(error, status=400):
        return JsonResponse({"error": error}, status=status)

    credential = request.POST.get("credential") or ""
    if not credential:
        return _json("Missing Google credential.")

    claims = verify_google_id_token(credential)  # <-- backend API verification
    if not claims:
        return _json("Google sign-in could not be verified. Please try again.", 401)

    email = (claims.get("email") or "").strip().casefold()
    if not email:
        return _json("Your Google account did not share an email address.", 401)
    email_verified = google_email_is_verified(claims.get("email_verified"))

    user = EmailUser.objects.filter(email__iexact=email).first()
    if user is None:
        if not email_verified:
            return _json(
                "Your Google email address is unverified, so an account cannot "
                "be created automatically.",
                403,
            )
        # Auto-signup: derive a unique username from the email's local part.
        base_username = slugify(email.split("@")[0]) or "user"
        username = base_username
        suffix = 1
        while EmailUser.objects.filter(username__iexact=username).exists():
            suffix += 1
            username = f"{base_username}{suffix}"
        user = EmailUser.objects.create_user(
            username=username,
            email=email,
            full_name=(claims.get("name") or username)[:150],
            password=EmailUser.objects.make_random_password(),
        )
    elif not email_verified:
        # SECURITY: never log into an existing account on an unverified email.
        return _json(
            "An account with this email already exists, but the email from your "
            "Google account is unverified. Please sign in with your password.",
            403,
        )

    if not user.is_active:
        return _json("This account has been deactivated.", 403)

    login(request, user, backend="accounts.backends.UsernameOrEmailBackend")

    # Decode-only payload is safe to echo back for UI display; auth is session based.
    profile = {
        "name": claims.get("name") or user.full_name or user.username,
        "email": email,
        "picture": claims.get("picture") or "",
    }
    return JsonResponse({"ok": True, "redirect": _login_redirect_url(request, user), "user": profile})


def _password_reset_context():
    return {
        "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
        "navigation_sections": _public_navigation_sections(),
        **_public_footer_context(),
    }


class CustomPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/password_reset_email.txt"
    html_email_template_name = "accounts/password_reset_email.html"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_password_reset_context())
        return context


class CustomPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_password_reset_context())
        return context


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_password_reset_context())
        return context


class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_password_reset_context())
        return context


def signup_view(request):
    if request.user.is_authenticated:
        return redirect(_dashboard_url(request.user))
    if request.method == "GET":
        return _auth_page(request, mode="signup")
    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])

    form = SignupForm(request.POST)
    if not form.is_valid():
        return _auth_page(request, mode="signup", signup_form=form)

    try:
        with transaction.atomic():
            user = EmailUser.objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                full_name=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
            )
    except IntegrityError:
        duplicate = EmailUser.objects.filter(
            email__iexact=form.cleaned_data["email"]
        ).exists()
        form.add_error(
            "email" if duplicate else "username",
            "An account with this email address already exists."
            if duplicate
            else "This username is already taken.",
        )
        return _auth_page(request, mode="signup", signup_form=form)

    login(request, user, backend="accounts.backends.UsernameOrEmailBackend")
    return redirect("accounts:dashboard")


@login_required
def dashboard(request):
    if request.user.is_superuser:
        return redirect("site_management:dashboard")
    profile_form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST":
        if profile_form.is_valid():
            profile_form.save()
            messages.success(
                request,
                "Your eligibility profile has been updated. Exam eligibility now uses these details.",
            )
            return redirect("accounts:dashboard")
    return render(
        request,
        "accounts/dashboard.html",
        {
            "profile_form": profile_form,
            "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
            "navigation_sections": _public_navigation_sections(),
            **_public_footer_context(),
        },
    )


@login_required
@require_POST
def logout_view(request):
    logout(request)
    return redirect("home")


def website_page(request, page_type):
    """View for About Us, Privacy Policy, Terms, Disclaimer, and Content Details pages."""
    if page_type == WebsitePage.PageType.CONTACT_US:
        return contact_us(request)
    return _website_page(request, page_type)


@login_required
def contact_us(request):
    return _website_page(request, WebsitePage.PageType.CONTACT_US)


def _website_page(request, page_type):
    page = WebsitePage.objects.filter(
        page_type=page_type,
        is_published=True,
    ).first()

    # If no published page found, check whether one exists but is unpublished.
    # An explicitly unpublished page is a 404 — the fallback is only for pages
    # that have never been created in the CMS at all.
    if page is None:
        db_record_exists = WebsitePage.objects.filter(page_type=page_type).exists()
        if db_record_exists:
            return _public_not_found(request)
        page = _get_fallback_page_content(page_type)
        if page is None:
            return _public_not_found(request)

    contact_form = None
    if page_type == WebsitePage.PageType.CONTACT_US:
        form_data = request.POST if request.method == "POST" else None
        contact_form = ContactMessageForm(form_data)
        if request.method == "POST" and contact_form.is_valid():
            contact_form.save()
            messages.success(request, "Your message has been sent.")
            return redirect("contact_us")

    website_settings = WebsiteSettings.objects.first() or WebsiteSettings()

    navigation_sections = []  # Public menu is a fixed allowlist in base_public.html
    footer_sections = list(
        ContentSection.objects.filter(
            area=ContentSection.Area.FOOTER,
            is_active=True,
        ).prefetch_related(
            Prefetch(
                "items",
                queryset=_public_content_items(),
            )
        )
    )
    available_slugs = set(
        ContentSection.objects.filter(
            area=ContentSection.Area.HOMEPAGE,
            is_active=True,
        ).values_list("slug", flat=True)
    )
    _attach_category_listing_urls(footer_sections, available_slugs)
    _attach_link_icon_styles(footer_sections)

    return render(
        request,
        "accounts/website_page.html",
        {
            "page": page,
            "contact_form": contact_form,
            "website_settings": website_settings,
            "navigation_sections": navigation_sections,
            "footer_sections": footer_sections,
            **_public_footer_context(footer_sections),
        },
    )


def _get_fallback_page_content(page_type):
    """Provide fallback content for informational pages not yet in CMS."""
    fallback_content = {
        WebsitePage.PageType.ABOUT_US: {
            "title": "About Us",
            "subtitle": "Your trusted source for government job information",
            "description": (
                "Welcome to Sarkari Result, your comprehensive portal for government job "
                "notifications, exam results, admit cards, answer keys, and recruitment updates.\n\n"
                "Our mission is to provide clear, accurate, and timely information about "
                "government job opportunities across various sectors including banking, railways, "
                "defence, teaching, and more.\n\n"
                "We aggregate information from official government websites and authorized sources "
                "to help job seekers find relevant opportunities without having to visit multiple sites.\n\n"
                "Please note: This is an informational portal. We are not affiliated with any "
                "government organization. Always verify official recruitment notifications on the "
                "respective government websites before applying."
            ),
        },
        WebsitePage.PageType.PRIVACY_POLICY: {
            "title": "Privacy Policy",
            "subtitle": "How we handle your information",
            "description": (
                "## Information We Collect\n\n"
                "When you use our website, we may collect the following information:\n\n"
                "- **Account Information**: If you create an account, we store your username, "
                "email address, and authentication credentials securely.\n"
                "- **Contact Messages**: When you send us a message through our contact form, "
                "we store your name, email address, subject, and message content.\n"
                "- **Usage Data**: We may collect anonymous usage data such as page views, "
                "browser type, and device information for analytics purposes.\n\n"
                "## How We Use Your Information\n\n"
                "We use your information to:\n\n"
                "- Provide and maintain our services\n"
                "- Respond to your inquiries and support requests\n"
                "- Improve our website and user experience\n"
                "- Send you important updates about our services (if you have an account)\n\n"
                "## Data Storage and Security\n\n"
                "We implement appropriate security measures to protect your personal information. "
                "Your data is stored securely and we never sell your information to third parties.\n\n"
                "## Cookies\n\n"
                "Our website uses essential cookies for authentication and session management. "
                "We may use analytics cookies to understand how visitors use our site. You can "
                "manage cookie preferences through your browser settings.\n\n"
                "## Your Rights\n\n"
                "You have the right to:\n\n"
                "- Access your personal data\n"
                "- Request correction of inaccurate data\n"
                "- Request deletion of your account and associated data\n"
                "- Opt out of non-essential communications\n\n"
                "## Third-Party Services\n\n"
                "Our website may include links to third-party websites. We are not responsible for "
                "the privacy practices of these external sites. We encourage you to review their "
                "privacy policies.\n\n"
                "## Changes to This Policy\n\n"
                "We may update this privacy policy from time to time. We will notify users of "
                "significant changes by posting the new policy on this page.\n\n"
                "## Contact Us\n\n"
                "If you have questions about this privacy policy or how we handle your data, "
                "please contact us through our Contact page."
            ),
        },
        WebsitePage.PageType.TERMS_AND_CONDITIONS: {
            "title": "Terms and Conditions",
            "subtitle": "Terms of use for this website",
            "description": (
                "## Acceptance of Terms\n\n"
                "By accessing and using Sarkari Result, you agree to be bound by these Terms "
                "and Conditions. If you do not agree to these terms, please do not use this website.\n\n"
                "## Purpose of This Website\n\n"
                "Sarkari Result is an informational portal that aggregates government job "
                "notifications, exam results, admit cards, and recruitment updates from official "
                "sources. We are not affiliated with any government organization.\n\n"
                "## Permitted Use\n\n"
                "You may use this website for:\n\n"
                "- Personal information and research purposes\n"
                "- Finding government job opportunities\n"
                "- Accessing publicly available recruitment information\n\n"
                "## Prohibited Uses\n\n"
                "You may not:\n\n"
                "- Use this website for any illegal purpose\n"
                "- Attempt to gain unauthorized access to our systems\n"
                "- Use automated tools to scrape or harvest data\n"
                "- Republish our content without proper attribution\n"
                "- Interfere with the operation of this website\n\n"
                "## Information Accuracy\n\n"
                "While we strive to provide accurate and up-to-date information, we cannot guarantee "
                "the completeness or accuracy of all content. Recruitment notifications, exam dates, "
                "eligibility criteria, and other details may change.\n\n"
                "**Always verify official information on the respective government websites before "
                "taking any action based on information found on this portal.**\n\n"
                "## External Links\n\n"
                "This website contains links to external government websites and third-party resources. "
                "We are not responsible for the content, privacy practices, or availability of these "
                "external sites.\n\n"
                "## Account Terms\n\n"
                "If you create an account:\n\n"
                "- You are responsible for maintaining the confidentiality of your account credentials\n"
                "- You must provide accurate and complete information\n"
                "- You must notify us of any unauthorized use of your account\n"
                "- We reserve the right to suspend or terminate accounts that violate these terms\n\n"
                "## Intellectual Property\n\n"
                "All content on this website, including text, graphics, logos, and software, is "
                "our property or the property of our licensors and is protected by copyright laws.\n\n"
                "## Limitation of Liability\n\n"
                "To the fullest extent permitted by law, we shall not be liable for any indirect, "
                "incidental, special, or consequential damages arising from your use of this website.\n\n"
                "## Indemnification\n\n"
                "You agree to indemnify and hold us harmless from any claims arising from your use "
                "of this website or violation of these terms.\n\n"
                "## Modifications to Terms\n\n"
                "We reserve the right to modify these terms at any time. Continued use of the website "
                "after changes constitutes acceptance of the new terms.\n\n"
                "## Governing Law\n\n"
                "These terms are governed by the laws of India. Any disputes shall be subject to the "
                "exclusive jurisdiction of the courts in India.\n\n"
                "## Contact Us\n\n"
                "For questions about these terms, please contact us through our Contact page."
            ),
        },
        WebsitePage.PageType.DISCLAIMER: {
            "title": "Disclaimer",
            "subtitle": "Important information about this portal",
            "description": (
                "## Nature of This Website\n\n"
                "Sarkari Result is an informational portal that aggregates government job "
                "notifications, exam results, admit cards, answer keys, and recruitment updates. "
                "We are NOT a government organization and we are NOT affiliated with any government "
                "department, ministry, or recruitment agency.\n\n"
                "## Information Accuracy\n\n"
                "The information provided on this website is for general informational purposes only. "
                "While we make every effort to ensure the accuracy of the information we publish, "
                "we cannot guarantee that all information is complete, current, or error-free.\n\n"
                "## Verify Official Sources\n\n"
                "**Important: Always verify all recruitment notifications, exam dates, eligibility "
                "criteria, application deadlines, and other details on the official government websites.**\n\n"
                "Links to official sources are provided wherever possible. Do not rely solely on "
                "information from this portal when making career decisions or submitting applications.\n\n"
                "## No Official Endorsement\n\n"
                "This website is not endorsed by, affiliated with, or connected to any government "
                "organization, recruitment board, or examination authority. All government logos, "
                "names, and trademarks are used for identification purposes only and remain the "
                "property of their respective owners.\n\n"
                "## Recruitment Information\n\n"
                "Job vacancies, exam results, admit cards, and other recruitment information are "
                "published by official government agencies. We aggregate this information from "
                "publicly available sources for user convenience. We do not influence recruitment "
                "decisions, exam results, or selection processes.\n\n"
                "## External Links\n\n"
                "This website contains links to external websites including official government "
                "portals. We are not responsible for the content, availability, or policies of "
                "these external sites. Accessing external links is at your own risk.\n\n"
                "## User Responsibility\n\n"
                "Users of this website are responsible for:\n\n"
                "- Verifying all information from official sources before taking action\n"
                "- Meeting eligibility criteria and application requirements\n"
                "- Submitting applications before official deadlines\n"
                "- Following official instructions for recruitment processes\n\n"
                "## Limitation of Liability\n\n"
                "In no event shall we be liable for any direct, indirect, incidental, special, "
                "or consequential damages arising from the use of this website or reliance on any "
                "information provided herein.\n\n"
                "## Changes to This Disclaimer\n\n"
                "We reserve the right to modify this disclaimer at any time. Changes will be posted "
                "on this page. Your continued use of the website constitutes acceptance of the "
                "updated disclaimer.\n\n"
                "## Contact Us\n\n"
                "If you have questions about this disclaimer or need clarification, please contact "
                "us through our Contact page."
            ),
        },
    }

    content = fallback_content.get(page_type)
    if content:
        return type('obj', (object,), {
            'title': content['title'],
            'subtitle': content['subtitle'],
            'description': content['description'],
            'page_type': page_type,
            'image': None,
            'image_alt': '',
            'image_caption': '',
            'link_url': '',
            'link_text': '',
            'contact_email': '',
            'contact_phone': '',
            'contact_address': '',
            'contact_hours': '',
        })()

    return None
