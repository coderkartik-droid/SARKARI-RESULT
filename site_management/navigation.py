"""Website Management sidebar navigation.

This module only *organises* the existing management screens into the fixed
workspace sections. The sidebar contains exactly seven exam-content sections
(Exams, Upcoming Exams, Recent Exams, Answer Sheet, Registration Form,
Previous Paper, Result) followed by the five website/system areas (Header,
Footer, Comments, Users, AI Assistant). It reuses existing views, URLs and
permissions — no models, routes or stored content are changed.
"""

from urllib.parse import urlsplit

from django.urls import NoReverseMatch, reverse
from django.utils.safestring import mark_safe


SUPERUSER = "superuser"


def sidebar_stats():
    """Lightweight counts used for sidebar badges (unread messages, pending comments)."""
    unread_messages = 0
    pending_comments = 0
    try:
        from .models import ContactSubmission

        unread_messages = ContactSubmission.objects.filter(is_read=False).count()
    except Exception:
        pass
    try:
        from comments.models import Comment

        pending_comments = Comment.objects.filter(status=Comment.Status.PENDING).count()
    except Exception:
        pass
    return {
        "unread_messages": unread_messages,
        "pending_comments": pending_comments,
    }


def _svg(paths):
    return mark_safe(
        '<svg class="management-nav-svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true" focusable="false">'
        + paths
        + "</svg>"
    )


ICONS = {
    "users": _svg(
        '<path d="M16 19v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 17.5V19"/>'
        '<circle cx="10" cy="8" r="3.2"/>'
        '<path d="M20.5 19v-1.4a3.4 3.4 0 0 0-2.6-3.3"/>'
        '<path d="M15.4 5.2a3.2 3.2 0 0 1 0 5.6"/>'
    ),
    "header": _svg(
        '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/>'
    ),
    "home": _svg(
        '<path d="M3 11.2 12 3.5l9 7.7"/><path d="M5.5 9.8V20h13V9.8"/>'
        '<path d="M9.8 20v-5.2h4.4V20"/>'
    ),
    "results": _svg(
        '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>'
        '<path d="M9 12.5h6"/><path d="M9 16h6"/>'
    ),
    "exams": _svg(
        '<path d="M22 10v6M2 10l10-5 10 5-10 5z"/>'
        '<path d="M6 12v5c3 3 9 3 12 0v-5"/>'
    ),
    "upcoming": _svg(
        '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18"/>'
        '<path d="M8 3v4M16 3v4"/><path d="M12 13v3.5M10.2 14.7h3.6"/>'
    ),
    "recent": _svg(
        '<circle cx="12" cy="12" r="9"/><path d="M12 7.5V12l3.2 2"/>'
    ),
    "jobs": _svg(
        '<rect x="3" y="7" width="18" height="13" rx="2"/>'
        '<path d="M8 7V5.4A1.4 1.4 0 0 1 9.4 4h5.2A1.4 1.4 0 0 1 16 5.4V7"/>'
        '<path d="M3 12h18"/>'
    ),
    "admit-card": _svg(
        '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10.8" r="2"/>'
        '<path d="M5.4 15.8c.6-1.3 1.8-2 3.1-2s2.5.7 3.1 2"/>'
        '<path d="M14 10h5"/><path d="M14 13.5h5"/>'
    ),
    "previous-papers": _svg(
        '<path d="M8.5 3h6.5l4 4v12h-10.5z"/><path d="M15 3v4h4"/>'
        '<path d="M6 6.5V21h9"/>'
    ),
    "answer-sheet": _svg(
        '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>'
        '<path d="m9.2 14.4 2 2 3.6-3.8"/>'
    ),
    "registration": _svg(
        '<rect x="3" y="5" width="18" height="14" rx="2"/>'
        '<path d="M7 15h4M7 11h7"/><path d="M15.5 15.5h1.5"/>'
    ),
    "tools": _svg(
        '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L4 17v3h3l5.3-5.3a4 4 0 0 0 5.4-5.4l-2.3 2.3-2-2z"/>'
    ),
    "footer": _svg(
        '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 15h18"/>'
    ),
    "ai": _svg(
        '<path d="M12 3.5l1.5 4.1 4.1 1.5-4.1 1.5L12 14.7l-1.5-4.1L6.4 9.1l4.1-1.5z"/>'
        '<path d="M18.4 15.4l.7 1.9 1.9.7-1.9.7-.7 1.9-.7-1.9-1.9-.7 1.9-.7z"/>'
    ),
    "comments": _svg(
        '<path d="M20 15a2 2 0 0 1-2 2H8l-4 3V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2z"/>'
    ),
}


SECTIONS = [
    {
        "key": "exams",
        "label": "Exams",
        "icon": "exams",
        "eyebrow": "EXAM ANNOUNCEMENTS",
        "title": "Exams",
        "description": (
            "Publish exam announcements with multiple PDF attachments, an exam date, "
            "an eligible date-of-birth window and the accepted qualifications."
        ),
        "view": "site_management:exams",
        "groups": [
            {
                "label": "Exam announcements",
                "items": [
                    {
                        "label": "All exams",
                        "view": "site_management:exams",
                    },
                    {
                        "label": "Add an exam",
                        "view": "site_management:exam_create",
                    },
                ],
            },
        ],
    },
    {
        "key": "upcoming-exams",
        "label": "Upcoming Exams",
        "icon": "upcoming",
        "eyebrow": "UPCOMING EXAMS",
        "title": "Upcoming Exams",
        "description": (
            "Exams that are genuinely upcoming according to their exam date. These "
            "are the same exam records shown under Exams — nothing is duplicated."
        ),
        "view": "site_management:upcoming_exams",
    },
    {
        "key": "recent-exams",
        "label": "Recent Exams",
        "icon": "recent",
        "eyebrow": "RECENT EXAMS",
        "title": "Recent Exams",
        "description": (
            "Recently published exam announcements, drawn from the same exam records "
            "using their publication dates."
        ),
        "view": "site_management:recent_exams",
    },
    {
        "key": "answer-sheets",
        "label": "Answer Sheet",
        "icon": "answer-sheet",
        "eyebrow": "ANSWER SHEETS",
        "title": "Answer Sheet",
        "description": (
            "Publish answer-sheet PDFs with their related exam. Upload the PDF, add "
            "optional instructions, and publish it to the public Answer Sheet page."
        ),
        "view": "site_management:resource_list",
        "args": ["answer-sheets"],
        "groups": [
            {
                "label": "Answer sheets",
                "items": [
                    {
                        "label": "All answer sheets",
                        "view": "site_management:resource_list",
                        "args": ["answer-sheets"],
                    },
                    {
                        "label": "Add an answer sheet",
                        "view": "site_management:resource_create",
                        "args": ["answer-sheets"],
                    },
                ],
            },
        ],
    },
    {
        "key": "registration-forms",
        "label": "Registration Form",
        "icon": "registration",
        "eyebrow": "REGISTRATION FORMS",
        "title": "Registration Form",
        "description": (
            "Publish application resources: a downloadable application PDF, an "
            "official application link, or both, with the last date to apply."
        ),
        "view": "site_management:resource_list",
        "args": ["registration-forms"],
        "groups": [
            {
                "label": "Registration resources",
                "items": [
                    {
                        "label": "All registration forms",
                        "view": "site_management:resource_list",
                        "args": ["registration-forms"],
                    },
                    {
                        "label": "Add a registration form",
                        "view": "site_management:resource_create",
                        "args": ["registration-forms"],
                    },
                ],
            },
        ],
    },
    {
        "key": "previous-papers",
        "label": "Previous Paper",
        "icon": "previous-papers",
        "eyebrow": "PREVIOUS PAPERS",
        "title": "Previous Paper",
        "description": (
            "Publish previous-year question papers with a required PDF and the exam "
            "year. Published papers are downloadable from the public Previous Paper page."
        ),
        "view": "site_management:resource_list",
        "args": ["previous-papers"],
        "groups": [
            {
                "label": "Papers",
                "items": [
                    {
                        "label": "All previous papers",
                        "view": "site_management:resource_list",
                        "args": ["previous-papers"],
                    },
                    {
                        "label": "Add a previous paper",
                        "view": "site_management:resource_create",
                        "args": ["previous-papers"],
                    },
                ],
            },
        ],
    },
    {
        "key": "results",
        "label": "Result",
        "icon": "results",
        "eyebrow": "EXAM RESULTS",
        "title": "Result",
        "description": (
            "Publish exam and recruitment results. Each result has a title, an "
            "optional related exam, an official result URL and/or an optional PDF, "
            "a publication switch, and a publish date."
        ),
        "view": "site_management:resource_list",
        "args": ["results"],
        "groups": [
            {
                "label": "Result announcements",
                "items": [
                    {
                        "label": "All results",
                        "view": "site_management:resource_list",
                        "args": ["results"],
                    },
                    {
                        "label": "Add a result",
                        "view": "site_management:resource_create",
                        "args": ["results"],
                    },
                ],
            },
        ],
    },
    {
        "key": "header",
        "label": "Header",
        "icon": "header",
        "eyebrow": "TOP OF THE WEBSITE",
        "title": "Header",
        "description": (
            "The top of every public page: website name and logo, tagline and favicon, "
            "header text, the navigation menu and dropdowns, the announcement strip, "
            "and header social icons."
        ),
        "groups": [
            {
                "label": "Brand & identity",
                "items": [
                    {
                        "label": "Name, logo, tagline & favicon",
                        "view": "site_management:settings",
                    },
                ],
            },
            {
                "label": "Navigation",
                "items": [
                    {
                        "label": "Menu links & dropdowns",
                        "view": "site_management:area_manager",
                        "args": ["navigation"],
                    },
                    {
                        "label": "Announcement strip",
                        "view": "site_management:area_manager",
                        "args": ["announcements"],
                    },
                ],
            },
            {
                "label": "Social",
                "items": [
                    {
                        "label": "Header social icons",
                        "view": "site_management:social_profiles",
                    },
                ],
            },
        ],
    },
    {
        "key": "footer",
        "label": "Footer",
        "icon": "footer",
        "eyebrow": "BOTTOM OF THE WEBSITE",
        "title": "Footer",
        "description": (
            "The bottom of every public page: footer description and contact details, "
            "footer columns and links, social profiles, copyright, and disclaimer text."
        ),
        "groups": [
            {
                "label": "Footer content",
                "items": [
                    {
                        "label": "Description, contact & copyright",
                        "view": "site_management:settings",
                    },
                    {
                        "label": "Footer columns & links",
                        "view": "site_management:area_manager",
                        "args": ["footer"],
                    },
                ],
            },
            {
                "label": "Social & legal",
                "items": [
                    {
                        "label": "Footer social profiles",
                        "view": "site_management:social_profiles",
                    },
                    {
                        "label": "Information pages (About, Contact, Privacy, Terms)",
                        "view": "site_management:website_pages",
                    },
                ],
            },
            {
                "label": "Pages & messages",
                "items": [
                    {
                        "label": "Contact messages",
                        "view": "site_management:contact_messages",
                        "badge": "unread_messages",
                    },
                    {
                        "label": "Extra content links",
                        "view": "site_management:content_links",
                    },
                ],
            },
        ],
    },
    {
        "key": "comments",
        "label": "Comments",
        "icon": "comments",
        "eyebrow": "COMMUNITY MODERATION",
        "title": "Comments",
        "description": (
            "Moderate community comments — approve, reject, or delete visitor "
            "submissions using the existing moderation permissions."
        ),
        "view": "site_management:comment_moderation",
        "badge": "pending_comments",
    },
    {
        "key": "users",
        "label": "Users",
        "icon": "users",
        "eyebrow": "PEOPLE & PERMISSIONS",
        "title": "Users",
        "description": (
            "Everyone who can sign in to your website — public members plus staff and "
            "administrator accounts. Search, review account status, and adjust sign-in "
            "and staff access from inside this workspace."
        ),
        "requires": "perm:accounts.view_emailuser",
        "view": "site_management:user_list",
    },
    {
        "key": "ai",
        "label": "AI Assistant",
        "icon": "ai",
        "eyebrow": "AI ASSISTANT",
        "title": "AI Assistant",
        "description": (
            "Monitor the public AI chatbot. Provider, model, and usage are read-only "
            "here, and API keys are never displayed."
        ),
        "view": "site_management:ai_status",
    },
]


def _path_of(url):
    return urlsplit(url).path


def _allowed(requires, user):
    if not requires:
        return True
    if requires == SUPERUSER:
        return bool(user and getattr(user, "is_superuser", False))
    if requires.startswith("perm:"):
        codename = requires[len("perm:"):]
        return bool(
            user
            and getattr(user, "is_active", False)
            and (getattr(user, "is_superuser", False) or user.has_perm(codename))
        )
    return True


def _resolve_item(item, user, current_path, stats):
    if not _allowed(item.get("requires"), user):
        return None

    if item.get("admin"):
        try:
            path = reverse(item["admin"])
        except NoReverseMatch:
            return None
        return {
            "label": item["label"],
            "url": path + item.get("query", ""),
            "external": True,
            "active": False,
            "badge": None,
        }

    if item.get("view"):
        try:
            path = reverse(item["view"], args=item.get("args", []))
        except NoReverseMatch:
            return None
        anchor = item.get("anchor")
        url = f"{path}#{anchor}" if anchor else path
        badge_key = item.get("badge")
        return {
            "label": item["label"],
            "url": url,
            "external": bool(item.get("external")),
            "active": _path_of(url) == current_path,
            "badge": stats.get(badge_key) if badge_key else None,
        }

    return None


def build_navigation(user, current_path="", stats=None):
    """Return the top-level sidebar sections resolved for ``user``.

    Items a user cannot access (for example Django admin links for
    non-superusers) are omitted so the sidebar never shows a dead link.
    """
    stats = stats if stats is not None else sidebar_stats()
    sections = []

    for raw in SECTIONS:
        if not _allowed(raw.get("requires"), user):
            continue
        groups = []
        all_items = []
        for group in raw.get("groups", []):
            items = []
            for item in group["items"]:
                resolved = _resolve_item(item, user, current_path, stats)
                if resolved:
                    items.append(resolved)
                    all_items.append(resolved)
            if items:
                groups.append({"label": group.get("label"), "items": items})

        if raw.get("view"):
            try:
                url = reverse(raw["view"], args=raw.get("args", []))
            except NoReverseMatch:
                continue
            if raw.get("anchor"):
                url = f"{url}#{raw['anchor']}"
            external = bool(raw.get("external"))
        else:
            url = reverse("site_management:section_overview", args=[raw["key"]])
            external = False

        badge_key = raw.get("badge")
        active = any(item["active"] for item in all_items) or _path_of(url) == current_path

        sections.append(
            {
                "key": raw["key"],
                "label": raw["label"],
                "icon": ICONS.get(raw.get("icon")),
                "eyebrow": raw.get("eyebrow", "WEBSITE MANAGEMENT"),
                "title": raw["title"],
                "description": raw.get("description", ""),
                "empty_message": raw.get("empty_message", ""),
                "url": url,
                "external": external,
                "badge": stats.get(badge_key) if badge_key else None,
                "has_submenu": bool(raw.get("groups")),
                "groups": groups,
                "active": active,
            }
        )

    return sections
