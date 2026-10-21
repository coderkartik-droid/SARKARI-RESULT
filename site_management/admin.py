from django import forms
from django.contrib import admin
from django.db import models as django_models
from django.utils.html import format_html
from urllib.parse import urlsplit

from .models import (
    AnswerSheet,
    ContactSubmission,
    ContentItem,
    ContentLink,
    ContentSection,
    Exam,
    ExamLink,
    ExamPDF,
    PreviousPaper,
    RegistrationResource,
    ResourceURL,
    Result,
    SocialMediaProfile,
    WebsitePage,
    WebsiteSettings,
)


class LinkTestAdminMixin:
    class Media:
        js = ("site_management/management_link_test.js",)


def external_link_icon(url, label):
    destination = (url or "").strip()
    if destination.startswith("/") and not destination.startswith("//"):
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer" '
            'aria-label="Open {} in a new tab">🔗</a>',
            destination,
            label,
        )
    if destination.startswith("#"):
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer" '
            'aria-label="Open {} in a new tab">🔗</a>',
            destination,
            label,
        )
    try:
        parsed = urlsplit(destination)
    except ValueError:
        return "—"
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        return "—"
    return format_html(
        '<a href="{}" target="_blank" rel="noopener noreferrer" '
        'aria-label="Open {} in a new tab">🔗</a>',
        url,
        label,
    )


class ContentItemInline(admin.TabularInline):
    model = ContentItem
    extra = 0
    fields = ("label", "url", "sort_order", "is_active", "open_new_tab")


@admin.register(ContentSection)
class ContentSectionAdmin(LinkTestAdminMixin, admin.ModelAdmin):
    list_display = ("title", "area", "sort_order", "is_active")
    list_filter = ("area", "is_active")
    search_fields = ("title", "slug")
    inlines = [ContentItemInline]

@admin.register(ContentItem)
class ContentItemAdmin(LinkTestAdminMixin, admin.ModelAdmin):
    list_display = (
        "display_title",
        "location_path",
        "section",
        "block_type",
        "sort_order",
        "is_active",
        "is_featured",
        "show_on_homepage",
    )
    list_filter = (
        "section__area",
        "section",
        "is_active",
        "is_featured",
        "show_on_homepage",
        "block_type",
    )
    search_fields = ("label", "body", "short_description", "subtitle")
    readonly_fields = (
        "image_preview",
        "secondary_image_preview",
        "thumbnail_image_preview",
    )
    fieldsets = (
        (
            "Basic Content",
            {
                "fields": (
                    "section",
                    "parent",
                    "label",
                    "title_color",
                    "title_background_color",
                    "subtitle",
                    "subtitle_color",
                    "subtitle_background_color",
                    "eyebrow_text",
                    "badge_text",
                    "highlight_text",
                    "short_description",
                    "body",
                    "additional_description",
                    "caption",
                    "source_name",
                    "published_at",
                ),
            },
        ),
        (
            "Links and Buttons",
            {
                "classes": ("collapse",),
                "fields": (
                    "url",
                    "primary_link_text",
                    "secondary_link_text",
                    "secondary_link_url",
                    "button_text",
                    "button_url",
                    "call_to_action",
                    "link_title",
                    "accessible_label",
                    "style",
                    "open_new_tab",
                ),
            },
        ),
        (
            "Images and Media",
            {
                "classes": ("collapse",),
                "fields": (
                    "image",
                    "image_preview",
                    "image_alt",
                    "image_caption",
                    "image_position",
                    "image_alignment",
                    "image_size",
                    "image_fit",
                    "secondary_image",
                    "secondary_image_preview",
                    "thumbnail_image",
                    "thumbnail_image_preview",
                ),
            },
        ),
        (
            "Appearance and Layout",
            {
                "classes": ("collapse",),
                "fields": (
                    "block_type",
                    "layout",
                    "icon",
                    "background_color",
                    "text_color",
                    "border_color",
                    "border_radius",
                    "spacing",
                    "content_alignment",
                    "badge_color",
                    "custom_css_class",
                    "show_on_desktop",
                    "show_on_tablet",
                    "show_on_mobile",
                ),
            },
        ),
        (
            "Publishing",
            {
                "classes": ("collapse",),
                "fields": (
                    "sort_order",
                    "is_active",
                    "is_featured",
                    "show_on_homepage",
                    "publish_at",
                    "expires_at",
                    "internal_notes",
                ),
            },
        ),
    )

    @admin.display(description="Title / Description")
    def display_title(self, obj):
        if obj.label:
            return obj.label
        if obj.body:
            return (obj.body[:35] + "...") if len(obj.body) > 35 else obj.body
        return f"Block #{obj.pk}"

    @admin.display(description="Location")
    def location_path(self, obj):
        return obj.location_path

    @admin.display(description="Primary image preview")
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:80px; max-width:140px; object-fit:contain; border-radius:6px; border:1px solid #cbd5e1; background:#f8fafc; padding:2px;" alt="Primary image preview">',
                obj.image.url,
            )
        return "No image uploaded"

    @admin.display(description="Secondary image preview")
    def secondary_image_preview(self, obj):
        if obj.secondary_image:
            return format_html(
                '<img src="{}" style="max-height:80px; max-width:140px; object-fit:contain; border-radius:6px; border:1px solid #cbd5e1; background:#f8fafc; padding:2px;" alt="Secondary image preview">',
                obj.secondary_image.url,
            )
        return "No secondary image uploaded"

    @admin.display(description="Thumbnail preview")
    def thumbnail_image_preview(self, obj):
        if obj.thumbnail_image:
            return format_html(
                '<img src="{}" style="max-height:80px; max-width:140px; object-fit:contain; border-radius:6px; border:1px solid #cbd5e1; background:#f8fafc; padding:2px;" alt="Thumbnail preview">',
                obj.thumbnail_image.url,
            )
        return "No thumbnail uploaded"


@admin.register(WebsiteSettings)
class WebsiteSettingsAdmin(LinkTestAdminMixin, admin.ModelAdmin):
    def has_add_permission(self, request):
        return not WebsiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContentLink)
class ContentLinkAdmin(LinkTestAdminMixin, admin.ModelAdmin):
    list_display = ("content_item", "label", "url_link", "is_active", "display_order", "starts_at", "ends_at")
    list_filter = ("is_active", "content_item__section")
    search_fields = ("label", "url", "description")
    ordering = ("content_item__section", "display_order", "pk")

    @admin.display(description="URL")
    def url_link(self, obj):
        return external_link_icon(obj.url, "Open content link")


@admin.register(SocialMediaProfile)
class SocialMediaProfileAdmin(LinkTestAdminMixin, admin.ModelAdmin):
    list_display = ("platform", "display_location", "is_active", "display_order", "profile_url_link")
    list_filter = ("platform", "display_location", "is_active")
    search_fields = ("platform", "profile_url", "accessible_label")
    ordering = ("display_order", "platform")

    @admin.display(description="Profile URL")
    def profile_url_link(self, obj):
        return external_link_icon(obj.profile_url, "Open social profile")


@admin.register(ContactSubmission)
class ContactSubmissionAdmin(admin.ModelAdmin):
    list_display = ("name", "phone_number", "email", "subject", "created_at", "is_read")
    list_filter = ("is_read", "created_at")
    search_fields = ("name", "phone_number", "email", "subject", "message")
    readonly_fields = ("name", "phone_number", "email", "subject", "message", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(WebsitePage)
class WebsitePageAdmin(LinkTestAdminMixin, admin.ModelAdmin):
    list_display = ("title", "page_type", "is_published", "updated_at")
    list_filter = ("page_type", "is_published")
    search_fields = ("title", "description")
    readonly_fields = ("image_preview",)
    fieldsets = (
        (None, {
            "fields": ("page_type", "title", "subtitle", "description", "is_published")
        }),
        ("Image", {
            "fields": ("image", "image_preview", "image_alt", "image_caption"),
            "classes": ("collapse",)
        }),
        ("Link", {
            "fields": ("link_url", "link_text"),
            "classes": ("collapse",)
        }),
        ("Contact Details", {
            "fields": (
                "contact_email",
                "contact_phone",
                "contact_address",
                "contact_hours",
                "contact_intro",
                "contact_facebook_url",
                "contact_instagram_url",
                "contact_whatsapp_url",
            ),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Image preview")
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:120px; max-width:240px; object-fit:contain;" alt="Website page image preview">',
                obj.image.url,
            )
        return "No image uploaded"


class ExamPDFInline(admin.TabularInline):
    model = ExamPDF
    extra = 0
    fields = ("display_name", "pdf_file", "external_link", "link_text", "sort_order", "is_active")


class ExamLinkInline(admin.TabularInline):
    """Edit every URL attached to an exam, with rows added on demand."""

    model = ExamLink
    extra = 1
    fields = ("link_text", "url", "icon_type", "sort_order", "is_active")


class ResourceURLInline(admin.TabularInline):
    """Edit multiple URLs attached to a resource (AnswerSheet, PreviousPaper, etc.)."""

    model = ResourceURL
    extra = 1
    fields = ("label", "url", "target", "sort_order", "is_active")


@admin.register(Exam)
class ExamAdmin(LinkTestAdminMixin, admin.ModelAdmin):
    list_display = ("title", "status", "is_published", "publish_at", "expires_at", "dob_start_date", "dob_end_date", "sort_order", "is_active")
    list_filter = ("status", "is_active", "publish_at", "expires_at", "eligible_qualifications")
    search_fields = ("title", "description")
    inlines = [ExamPDFInline, ExamLinkInline]
    # Render the multi-select qualifications field as clickable checkboxes so
    # several options can be picked without Ctrl/Cmd or a dual-list selector.
    formfield_overrides = {
        django_models.ManyToManyField: {"widget": forms.CheckboxSelectMultiple},
    }
    readonly_fields = ("is_published",)

    @admin.display(description="Published")
    def is_published(self, obj):
        return obj.is_published


@admin.register(ExamPDF)
class ExamPDFAdmin(LinkTestAdminMixin, admin.ModelAdmin):
    list_display = ("display_name", "exam", "pdf_link", "external_link", "sort_order", "is_active")
    list_filter = ("is_active", "exam")
    search_fields = ("display_name", "exam__title")

    @admin.display(description="PDF")
    def pdf_link(self, obj):
        if obj.pdf_file:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">📄 View PDF</a>',
                obj.pdf_file.url,
            )
        return "No PDF"


@admin.register(ExamLink)
class ExamLinkAdmin(LinkTestAdminMixin, admin.ModelAdmin):
    list_display = ("link_text", "exam", "icon_type", "url_link", "sort_order", "is_active")
    list_filter = ("icon_type", "is_active", "exam")
    search_fields = ("link_text", "url", "exam__title")
    ordering = ("exam", "sort_order", "pk")

    @admin.display(description="URL")
    def url_link(self, obj):
        return external_link_icon(obj.url, "Open exam link")


@admin.register(ResourceURL)
class ResourceURLAdmin(LinkTestAdminMixin, admin.ModelAdmin):
    list_display = ("label", "content_type", "object_id", "target", "url_link", "sort_order", "is_active")
    list_filter = ("target", "is_active", "content_type__model")
    search_fields = ("label", "url")
    ordering = ("content_type", "object_id", "sort_order", "pk")

    @admin.display(description="URL")
    def url_link(self, obj):
        return external_link_icon(obj.url, "Open resource URL")


# ── Exam-linked resource models ───────────────────────────────────────────────
# These four models are also managed through the custom CMS at /site-management/.
# Registering them here gives administrators an alternative Django admin path at
# /admin/ with the same publish/draft workflow.

@admin.register(AnswerSheet)
class AnswerSheetAdmin(admin.ModelAdmin):
    list_display = ("title", "exam", "status", "is_active", "published_date", "sort_order", "created_at")
    list_filter = ("status", "is_active", "exam")
    search_fields = ("title", "description", "exam__title")
    ordering = ("sort_order", "-created_at")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {
            "fields": ("title", "exam", "description", "pdf_file"),
        }),
        ("Publishing", {
            "fields": ("status", "published_date", "sort_order", "is_active"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(RegistrationResource)
class RegistrationResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "exam", "status", "is_active", "published_date", "closing_date", "sort_order", "created_at")
    list_filter = ("status", "is_active", "exam")
    search_fields = ("title", "description", "exam__title")
    ordering = ("sort_order", "-created_at")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {
            "fields": ("title", "exam", "description", "pdf_file", "official_url", "closing_date"),
        }),
        ("Publishing", {
            "fields": ("status", "published_date", "sort_order", "is_active"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(PreviousPaper)
class PreviousPaperAdmin(admin.ModelAdmin):
    list_display = ("title", "exam", "exam_year", "status", "is_active", "published_date", "sort_order", "created_at")
    list_filter = ("status", "is_active", "exam", "exam_year")
    search_fields = ("title", "description", "exam__title")
    ordering = ("sort_order", "-created_at")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {
            "fields": ("title", "exam", "exam_year", "description", "pdf_file"),
        }),
        ("Publishing", {
            "fields": ("status", "published_date", "sort_order", "is_active"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ("title", "exam", "status", "is_active", "published_date", "sort_order", "created_at")
    list_filter = ("status", "is_active", "exam")
    search_fields = ("title", "description", "exam__title")
    ordering = ("sort_order", "-created_at")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {
            "fields": ("title", "exam", "description", "official_url", "pdf_file"),
        }),
        ("Publishing", {
            "fields": ("status", "published_date", "sort_order", "is_active"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
