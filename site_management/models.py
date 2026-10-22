import os
import warnings
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction
from django.core.validators import RegexValidator
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image, UnidentifiedImageError

from .icons import KNOWN_ICONS


MAX_CONTENT_IMAGE_SIZE = 5 * 1024 * 1024
MAX_CONTENT_PDF_SIZE = 20 * 1024 * 1024
SUPPORTED_CONTENT_IMAGE_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})
HEX_COLOR_VALIDATOR = RegexValidator(
    regex=r"\A#[0-9A-Fa-f]{6}\Z",
    message="Enter a six-digit hexadecimal color, such as #336699.",
)
CSS_CLASS_VALIDATOR = RegexValidator(
    regex=r"\A[A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z][A-Za-z0-9_-]*)*\Z",
    message="Use CSS class names containing only letters, numbers, hyphens, and underscores.",
)


def validate_content_image(image):
    if not image:
        return

    max_size = getattr(settings, "CMS_MAX_IMAGE_SIZE", MAX_CONTENT_IMAGE_SIZE)
    if image.size > max_size:
        max_size_mb = max_size / (1024 * 1024)
        raise ValidationError(f"Choose an image no larger than {max_size_mb:g} MB.")

    try:
        image.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(image) as opened_image:
                image_format = opened_image.format
                if image_format not in SUPPORTED_CONTENT_IMAGE_FORMATS:
                    raise ValidationError(
                        "Supported image formats are PNG, JPG, JPEG, and WebP."
                    )
                opened_image.verify()
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValidationError(
            "Upload a valid, uncorrupted PNG, JPG, JPEG, or WebP image."
        ) from error
    finally:
        image.seek(0)


def validate_content_pdf(file):
    """Accept a PDF file only: extension, ``%PDF-`` signature, and size limit.

    The signature check rejects renamed non-PDF uploads, and the declared
    extension check keeps stored filenames predictable. The size limit is read
    from ``CMS_MAX_PDF_SIZE`` (default 20 MB).
    """
    if not file:
        return

    max_size = getattr(settings, "CMS_MAX_PDF_SIZE", MAX_CONTENT_PDF_SIZE)
    if file.size and file.size > max_size:
        max_size_mb = max_size / (1024 * 1024)
        raise ValidationError(f"Choose a PDF no larger than {max_size_mb:g} MB.")

    name = getattr(file, "name", "") or ""
    if not name.lower().endswith(".pdf"):
        raise ValidationError("Upload a PDF file (the filename must end in .pdf).")

    try:
        file.seek(0)
        signature = file.read(5)
    except (AttributeError, OSError, ValueError) as error:
        raise ValidationError("Upload a valid, uncorrupted PDF file.") from error
    finally:
        try:
            file.seek(0)
        except (AttributeError, OSError, ValueError):
            pass

    if signature != b"%PDF-":
        raise ValidationError("Upload a valid, uncorrupted PDF file.")


def validate_public_url(value):
    if not value:
        return

    value = value.strip()

    # Reject dangerous URL schemes
    if value.lower().startswith(("javascript:", "data:", "vbscript:", "file:", "ftp:")):
        raise ValidationError("This URL scheme is not allowed for security reasons.")

    if value.startswith("#"):
        if any(character.isspace() for character in value):
            raise ValidationError("Enter a valid anchor link.")
        return

    if value.startswith("/"):
        if value.startswith("//") or "\\" in value:
            raise ValidationError("Internal links must be local paths.")
        return

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValidationError("Use a valid HTTP/HTTPS URL.") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValidationError("Use a local path or an HTTP/HTTPS URL.")


class SafePDFUploadTo:
    """Serializable ``upload_to`` callable used by the exam-resource models.

    Implemented as a deconstructable class (rather than a plain closure) so that
    Django can serialize it into migrations by import path. It keeps only the
    basename of the uploaded filename, slugifies it into a predictable ASCII
    form, and normalizes the extension — preventing directory-traversal names.
    Configured storage still de-duplicates names, so no existing file is ever
    overwritten.
    """

    def __init__(self, subdirectory):
        self.subdirectory = subdirectory

    def __call__(self, instance, filename):
        base = os.path.basename(filename or "")
        stem, extension = os.path.splitext(base)
        safe_stem = slugify(stem)[:80] or "document"
        safe_extension = extension.lower() or ".pdf"
        return f"{self.subdirectory}/{safe_stem}{safe_extension}"

    def deconstruct(self):
        return ("site_management.models.SafePDFUploadTo", [self.subdirectory], {})



class WebsiteSettings(models.Model):
    site_name = models.CharField(max_length=100, default="Sarkari Result")
    tagline = models.CharField(
        max_length=180,
        default="Government Jobs, Results & Exam Updates",
    )
    logo_text = models.CharField(max_length=12, default="SR")
    logo_url = models.CharField(
        max_length=500,
        blank=True,
        validators=[validate_public_url],
    )
    favicon_url = models.CharField(
        max_length=500,
        blank=True,
        validators=[validate_public_url],
    )
    header_text = models.CharField(
        max_length=180,
        default="EXAM & RECRUITMENT DESK",
    )
    hero_title = models.CharField(
        max_length=240,
        default="Your gateway to government jobs.",
    )
    hero_description = models.TextField(
        default=(
            "Find recruitment updates, exam results, admit cards, answer keys, "
            "and preparation resources in one clear place."
        )
    )
    announcement = models.CharField(max_length=300, blank=True)
    # Editorial-note and footer copy default to empty so the public site never
    # ships placeholder/"demo" text. Admins opt in by filling these in.
    hero_note_title = models.CharField(max_length=120, blank=True, default="")
    hero_note_body = models.TextField(blank=True, default="")
    hero_note_footer = models.CharField(max_length=240, blank=True, default="")
    footer_description = models.TextField(blank=True, default="")
    footer_contact = models.CharField(
        max_length=240,
        default="Contact details have not been configured.",
    )
    footer_copyright = models.CharField(max_length=180, default="Sarkari Result")
    footer_disclaimer = models.CharField(
        max_length=240,
        blank=True,
        default="",
    )
    text_styles = models.JSONField(
        blank=True,
        default=dict,
        help_text=(
            "Per-element presentation for the header, hero and footer text. "
            "Managed by the shared visual content editor; edited values are "
            "validated before saving."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Website settings"
        verbose_name_plural = "Website settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Website settings cannot be deleted.")

    def __str__(self):
        return self.site_name


class ContentSection(models.Model):
    class Area(models.TextChoices):
        NAVIGATION = "navigation", "Navigation"
        HOMEPAGE = "homepage", "Homepage"
        ANNOUNCEMENTS = "announcements", "Announcements"
        HERO_ACTIONS = "hero_actions", "Homepage buttons"
        TOOLS = "tools", "Tools landing page"
        FOOTER = "footer", "Footer"

    area = models.CharField(max_length=20, choices=Area.choices, blank=True, default=Area.HOMEPAGE)
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(
        "icon",
        max_length=30,
        blank=True,
        help_text="Pick a visual icon in the CMS form. Unknown legacy names fall back to a safe default.",
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    text_styles = models.JSONField(
        blank=True,
        default=dict,
        help_text=(
            "Per-element presentation for this section's heading and "
            "description. Managed by the shared visual content editor."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "pk"]
        indexes = [models.Index(fields=["area", "is_active", "sort_order"])]

    def __str__(self):
        return f"{self.get_area_display()}: {self.title}"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)[:90] or "section"
            slug = base_slug
            counter = 1
            while ContentSection.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        if not self.area:
            self.area = self.Area.HOMEPAGE
        super().save(*args, **kwargs)


class ContentItem(models.Model):
    class BlockType(models.TextChoices):
        STANDARD = "standard", "Standard"
        NOTICE = "notice", "Notice"
        FEATURE = "feature", "Featured"
        CALLOUT = "callout", "Callout"

    class ImagePosition(models.TextChoices):
        TOP_LEFT = "top-left", "Top left"
        TOP_RIGHT = "top-right", "Top right"
        LEFT = "left", "Left"
        RIGHT = "right", "Right"
        BACKGROUND = "background", "Background panel"

    class ImageSize(models.TextChoices):
        SMALL = "small", "Small"
        MEDIUM = "medium", "Medium"
        LARGE = "large", "Large"

    class ImageFit(models.TextChoices):
        CONTAIN = "contain", "Contain"
        COVER = "cover", "Cover"

    class BorderRadius(models.TextChoices):
        SMALL = "small", "Small"
        MEDIUM = "medium", "Medium"
        LARGE = "large", "Large"

    class Spacing(models.TextChoices):
        COMPACT = "compact", "Compact"
        NORMAL = "normal", "Normal"
        RELAXED = "relaxed", "Relaxed"

    class Alignment(models.TextChoices):
        LEFT = "left", "Left"
        CENTER = "center", "Center"
        RIGHT = "right", "Right"

    class Layout(models.TextChoices):
        CARD = "card", "Card"
        FEATURE = "feature", "Feature"
        COMPACT = "compact", "Compact"

    class BadgeColor(models.TextChoices):
        VIOLET = "violet", "Violet"
        BLUE = "blue", "Blue"
        CYAN = "cyan", "Cyan"
        GREEN = "green", "Green"
        AMBER = "amber", "Amber"
        ROSE = "rose", "Rose"

    class Style(models.TextChoices):
        LINK = "link", "Link"
        BUTTON = "button", "Button"

    section = models.ForeignKey(
        ContentSection,
        related_name="items",
        on_delete=models.CASCADE,
    )
    parent = models.ForeignKey(
        "self",
        related_name="children",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    label = models.CharField(
        "Title",
        max_length=140,
        blank=True,
        default="",
        help_text="Optional heading for this block.",
    )
    title_color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        validators=[HEX_COLOR_VALIDATOR],
        help_text="Optional HEX color for the display title.",
    )
    title_background_color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        validators=[HEX_COLOR_VALIDATOR],
        help_text="Optional HEX background behind the title.",
    )
    body = models.TextField(blank=True)
    subtitle = models.CharField(max_length=180, blank=True)
    subtitle_color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        validators=[HEX_COLOR_VALIDATOR],
        help_text="Optional HEX color for the subtitle text.",
    )
    subtitle_background_color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        validators=[HEX_COLOR_VALIDATOR],
        help_text="Optional HEX background behind the subtitle.",
    )
    short_description = models.CharField(max_length=280, blank=True)
    additional_description = models.TextField(blank=True)
    badge_text = models.CharField(max_length=60, blank=True)
    eyebrow_text = models.CharField(max_length=100, blank=True)
    highlight_text = models.CharField(max_length=180, blank=True)
    caption = models.CharField(max_length=240, blank=True)
    source_name = models.CharField(max_length=140, blank=True)
    published_at = models.DateField(null=True, blank=True)
    primary_link_text = models.CharField(max_length=100, blank=True)
    secondary_link_text = models.CharField(max_length=100, blank=True)
    secondary_link_url = models.CharField(
        max_length=500,
        blank=True,
        validators=[validate_public_url],
    )
    button_text = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Optional button label.",
    )
    button_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        validators=[validate_public_url],
        help_text="Optional button destination URL.",
    )
    call_to_action = models.CharField(max_length=180, blank=True)
    link_title = models.CharField(max_length=180, blank=True)
    accessible_label = models.CharField(max_length=180, blank=True)
    image = models.ImageField(
        upload_to="cms/content_items/",
        blank=True,
        validators=[validate_content_image],
        error_messages={
            "invalid_image": "Upload a valid, uncorrupted PNG, JPG, JPEG, or WebP image.",
        },
        help_text="Optional PNG, JPG, JPEG, or WebP image. Maximum size is configured with CMS_MAX_IMAGE_SIZE (default 5 MB).",
    )
    secondary_image = models.ImageField(
        upload_to="cms/content_items/",
        blank=True,
        validators=[validate_content_image],
        error_messages={"invalid_image": "Upload a valid, uncorrupted PNG, JPG, JPEG, or WebP image."},
        help_text="Optional secondary PNG, JPG, JPEG, or WebP image. Maximum size is configured with CMS_MAX_IMAGE_SIZE (default 5 MB).",
    )
    thumbnail_image = models.ImageField(
        upload_to="cms/content_items/",
        blank=True,
        validators=[validate_content_image],
        error_messages={"invalid_image": "Upload a valid, uncorrupted PNG, JPG, JPEG, or WebP image."},
        help_text="Optional thumbnail PNG, JPG, JPEG, or WebP image. Maximum size is configured with CMS_MAX_IMAGE_SIZE (default 5 MB).",
    )
    pdf_file = models.FileField(
        "PDF file",
        upload_to="cms/content_pdfs/",
        blank=True,
        validators=[validate_content_pdf],
        help_text=(
            "Optional PDF, e.g. a result, admit card, or previous-year paper. "
            "PDF only. Maximum size is configured with CMS_MAX_PDF_SIZE (default 20 MB)."
        ),
    )
    image_alt = models.CharField(max_length=180, blank=True)
    image_caption = models.CharField(max_length=240, blank=True)
    image_position = models.CharField(
        max_length=12,
        choices=ImagePosition.choices,
        blank=True,
        default="",
    )
    image_alignment = models.CharField(
        max_length=6,
        choices=Alignment.choices,
        blank=True,
        default="",
        help_text="Optional image alignment (left, center, or right).",
    )
    image_size = models.CharField(
        max_length=8,
        choices=ImageSize.choices,
        blank=True,
        default="",
    )
    image_fit = models.CharField(
        max_length=8,
        choices=ImageFit.choices,
        blank=True,
        default="",
    )
    url = models.CharField(
        max_length=500,
        blank=True,
        validators=[validate_public_url],
    )
    style = models.CharField(
        max_length=10,
        choices=Style.choices,
        blank=True,
        default=Style.LINK,
    )
    icon = models.CharField(
        "icon",
        max_length=30,
        blank=True,
        help_text="Pick a visual icon in the CMS form. Unknown legacy names fall back to a safe default.",
    )
    block_type = models.CharField(
        max_length=10,
        choices=BlockType.choices,
        blank=True,
        default="",
    )
    background_color = models.CharField(
        max_length=7,
        blank=True,
        validators=[HEX_COLOR_VALIDATOR],
    )
    text_color = models.CharField(
        max_length=7,
        blank=True,
        validators=[HEX_COLOR_VALIDATOR],
    )
    border_color = models.CharField(
        max_length=7,
        blank=True,
        validators=[HEX_COLOR_VALIDATOR],
    )
    border_radius = models.CharField(
        max_length=6,
        choices=BorderRadius.choices,
        blank=True,
        default="",
    )
    spacing = models.CharField(
        max_length=8,
        choices=Spacing.choices,
        blank=True,
        default="",
    )
    content_alignment = models.CharField(
        max_length=6,
        choices=Alignment.choices,
        blank=True,
        default="",
    )
    layout = models.CharField(
        max_length=8,
        choices=Layout.choices,
        blank=True,
        default="",
    )
    badge_color = models.CharField(
        max_length=8,
        choices=BadgeColor.choices,
        blank=True,
        default="",
    )
    custom_css_class = models.CharField(
        max_length=160,
        blank=True,
        validators=[CSS_CLASS_VALIDATOR],
    )
    show_on_desktop = models.BooleanField(default=True)
    show_on_tablet = models.BooleanField(default=True)
    show_on_mobile = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    show_on_homepage = models.BooleanField(default=True)
    publish_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    internal_notes = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(blank=True, default=0)
    open_new_tab = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    text_styles = models.JSONField(
        blank=True,
        default=dict,
        help_text=(
            "Per-element presentation (colour, size, weight, italic, "
            "alignment, spacing and order) for this block's text. Managed by "
            "the shared visual content editor; edited values are validated "
            "before saving."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "pk"]
        indexes = [
            models.Index(fields=["section", "is_active", "sort_order"]),
            models.Index(fields=["parent", "is_active", "sort_order"]),
        ]

    def save(self, *args, **kwargs):
        previous_image_names = {}
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(
                "image", "secondary_image", "thumbnail_image", "pdf_file"
            ).first()
            if previous:
                previous_image_names = previous

        super().save(*args, **kwargs)

        for field_name, previous_name in previous_image_names.items():
            current_name = getattr(self, field_name).name
            if previous_name and previous_name != current_name:
                storage = getattr(self, field_name).storage
                transaction.on_commit(
                    lambda name=previous_name, file_storage=storage: file_storage.delete(name)
                )

    def delete(self, *args, **kwargs):
        image_names = [
            (getattr(self, field_name).name, getattr(self, field_name).storage)
            for field_name in ("image", "secondary_image", "thumbnail_image", "pdf_file")
            if getattr(self, field_name)
        ]
        result = super().delete(*args, **kwargs)
        for image_name, storage in image_names:
            transaction.on_commit(
                lambda name=image_name, file_storage=storage: file_storage.delete(name)
            )
        return result

    def clean(self):
        super().clean()
        if self.parent_id:
            if self.parent_id == self.pk:
                raise ValidationError({"parent": "An item cannot be its own parent."})
            if self.parent.section_id != self.section_id:
                raise ValidationError(
                    {"parent": "Nested items must belong to the same section."}
                )
            if self.parent.parent_id:
                raise ValidationError(
                    {"parent": "Dropdown items must be attached to a top-level item."}
                )
            ancestor = self.parent
            while ancestor is not None:
                if ancestor.pk == self.pk:
                    raise ValidationError(
                        {"parent": "Nested menu items cannot contain a cycle."}
                    )
                ancestor = ancestor.parent
        validate_public_url(self.url)
        validate_public_url(self.secondary_link_url)
        validate_public_url(self.button_url)
        if self.section_id and hasattr(self, "section") and self.section.area == ContentSection.Area.HOMEPAGE and not (self.body and self.body.strip()):
            raise ValidationError({"body": "Description is required for homepage content blocks."})
        if self.publish_at and self.expires_at and self.expires_at <= self.publish_at:
            raise ValidationError({"expires_at": "Expiry must be later than the publish date."})

    @property
    def location_path(self):
        section_name = self.section.get_area_display() if self.section_id else "Unassigned"
        segment = self.label or self.body.strip()[:40] or f"Block #{self.pk or 'new'}"
        return f"{section_name} → {segment}"

    @property
    def location_label(self):
        return self.location_path

    def __str__(self):
        if self.label:
            return self.label
        if self.body:
            snippet = self.body.strip()
            return snippet[:47] + "..." if len(snippet) > 50 else snippet
        return f"Content block #{self.pk}" if self.pk else "New content block"


class ContentLink(models.Model):
    content_item = models.ForeignKey(
        "ContentItem",
        related_name="links",
        on_delete=models.CASCADE,
        help_text="Content block this link belongs to.",
    )
    label = models.CharField(max_length=120, help_text="Visible text shown to visitors.")
    url = models.CharField(
        max_length=500,
        validators=[validate_public_url],
        help_text="Local path or http/https URL.",
    )
    description = models.CharField(max_length=250, blank=True)
    icon = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Optional built-in icon identifier.",
    )
    icon_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        validators=[validate_public_url],
        help_text="Optional custom icon URL.",
    )
    icon_color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        validators=[HEX_COLOR_VALIDATOR],
        help_text="Optional icon color in HEX format.",
    )
    is_active = models.BooleanField(default=True)
    open_new_tab = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    text_styles = models.JSONField(
        blank=True,
        default=dict,
        help_text=(
            "Per-element presentation for this nested link's title, URL text "
            "and description. Managed by the shared visual content editor."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "pk"]
        verbose_name = "Content link"
        verbose_name_plural = "Content links"

    def clean(self):
        super().clean()
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "End date must be later than the start date."})
        validate_public_url(self.url)
        validate_public_url(self.icon_url)

    def __str__(self):
        return self.label or self.url


class SocialMediaProfile(models.Model):
    class Platform(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        INSTAGRAM = "instagram", "Instagram"
        FACEBOOK = "facebook", "Facebook"
        WHATSAPP = "whatsapp", "WhatsApp"

    class DisplayLocation(models.TextChoices):
        HEADER = "header", "Header"
        FOOTER = "footer", "Footer"
        BOTH = "both", "Header + Footer"

    platform = models.CharField(max_length=20, choices=Platform.choices, unique=True)
    profile_url = models.CharField(
        max_length=500,
        validators=[validate_public_url],
        help_text="Public profile or channel URL.",
    )
    custom_icon_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        validators=[validate_public_url],
        help_text="Optional custom icon image URL.",
    )
    built_in_icon = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Built-in icon identifier for the platform.",
    )
    icon_color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        validators=[HEX_COLOR_VALIDATOR],
        help_text="Optional HEX color for the platform icon.",
    )
    accessible_label = models.CharField(max_length=80, blank=True, default="")
    display_location = models.CharField(
        max_length=10,
        choices=DisplayLocation.choices,
        default=DisplayLocation.BOTH,
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "pk"]
        verbose_name = "Social media profile"
        verbose_name_plural = "Social media profiles"

    @property
    def display_name(self):
        return self.get_platform_display()

    def __str__(self):
        return self.display_name


DEFAULT_SOCIAL_PROFILE_SETTINGS = {
    SocialMediaProfile.Platform.INSTAGRAM: {
        "display_name": "Instagram",
        "profile_url": "https://www.instagram.com/",
        "built_in_icon": "instagram",
        "icon_color": "#E4405F",
        "accessible_label": "Instagram",
        "display_order": 0,
        "display_location": SocialMediaProfile.DisplayLocation.FOOTER,
    },
    SocialMediaProfile.Platform.WHATSAPP: {
        "display_name": "WhatsApp",
        "profile_url": "https://www.whatsapp.com/",
        "built_in_icon": "whatsapp",
        "icon_color": "#25D366",
        "accessible_label": "WhatsApp",
        "display_order": 1,
        "display_location": SocialMediaProfile.DisplayLocation.FOOTER,
    },
    SocialMediaProfile.Platform.FACEBOOK: {
        "display_name": "Facebook",
        "profile_url": "https://www.facebook.com/",
        "built_in_icon": "facebook",
        "icon_color": "#1877F2",
        "accessible_label": "Facebook",
        "display_order": 2,
        "display_location": SocialMediaProfile.DisplayLocation.FOOTER,
    },
}


class WebsitePage(models.Model):
    class PageType(models.TextChoices):
        ABOUT_US = "about_us", "About Us"
        CONTACT_US = "contact_us", "Contact Us"
        PRIVACY_POLICY = "privacy_policy", "Privacy Policy"
        TERMS_AND_CONDITIONS = "terms_and_conditions", "Terms and Conditions"
        DISCLAIMER = "disclaimer", "Disclaimer"
        CONTENT_DETAILS = "content_details", "Content Details"

    page_type = models.CharField(
        max_length=20,
        choices=PageType.choices,
        unique=True,
        help_text="Type of page (About Us, Privacy Policy, or Content Details)."
    )
    title = models.CharField(
        max_length=200,
        help_text="Page title (e.g., 'About Us')."
    )
    subtitle = models.CharField(
        max_length=300,
        blank=True,
        help_text="Optional subtitle or heading below the title."
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Main page content (optional)."
    )
    image = models.ImageField(
        upload_to="cms/website_pages/",
        blank=True,
        validators=[validate_content_image],
        error_messages={
            "invalid_image": "Upload a valid, uncorrupted PNG, JPG, JPEG, or WebP image.",
        },
        help_text="Optional PNG, JPG, JPEG, or WebP image. Maximum size is configured with CMS_MAX_IMAGE_SIZE (default 5 MB)."
    )
    image_alt = models.CharField(
        max_length=180,
        blank=True,
        help_text="Alt text for the image for accessibility."
    )
    image_caption = models.CharField(
        max_length=240,
        blank=True,
        help_text="Optional caption for the image."
    )
    link_url = models.CharField(
        max_length=500,
        blank=True,
        validators=[validate_public_url],
        help_text="Optional link URL."
    )
    link_text = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional link button text."
    )
    contact_email = models.EmailField(
        blank=True,
        help_text="Public contact email for the Contact Us page. Leave blank to hide."
    )
    contact_phone = models.CharField(
        max_length=40,
        blank=True,
        validators=[RegexValidator(regex=r"\A[0-9+()\-\s]{3,}\Z", message="Enter a valid phone number.")],
        help_text="Optional phone number shown on the Contact Us page."
    )
    contact_address = models.TextField(
        blank=True,
        help_text="Optional postal address shown on the Contact Us page."
    )
    contact_hours = models.CharField(
        max_length=240,
        blank=True,
        help_text="Optional office hours, e.g. 'Mon–Fri, 10 AM – 5 PM IST'."
    )
    contact_intro = models.TextField(
        blank=True,
        help_text="Optional introduction shown above the contact form."
    )
    contact_facebook_url = models.CharField(
        max_length=500,
        blank=True,
        validators=[validate_public_url],
        help_text="Optional Facebook page URL. Leave blank to hide the icon."
    )
    contact_instagram_url = models.CharField(
        max_length=500,
        blank=True,
        validators=[validate_public_url],
        help_text="Optional Instagram profile URL. Leave blank to hide the icon."
    )
    contact_whatsapp_url = models.CharField(
        max_length=500,
        blank=True,
        validators=[validate_public_url],
        help_text="Optional WhatsApp link, e.g. https://wa.me/919XXXXXXXXX. Leave blank to hide the icon."
    )
    is_published = models.BooleanField(
        default=True,
        help_text="Whether the page is visible to the public."
    )
    text_styles = models.JSONField(
        blank=True,
        default=dict,
        help_text=(
            "Per-element presentation for this page's title, subtitle and "
            "content. Managed by the shared visual content editor."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Website page"
        verbose_name_plural = "Website pages"
        ordering = ["page_type"]

    def __str__(self):
        return self.get_page_type_display()

    def get_slug(self):
        """Return the URL slug for this page type."""
        slug_map = {
            self.PageType.ABOUT_US: "about-us",
            self.PageType.CONTACT_US: "contact-us",
            self.PageType.PRIVACY_POLICY: "privacy-policy",
            self.PageType.TERMS_AND_CONDITIONS: "terms-and-conditions",
            self.PageType.DISCLAIMER: "disclaimer",
            self.PageType.CONTENT_DETAILS: "content-details",
        }
        return slug_map.get(self.page_type, "")

    def save(self, *args, **kwargs):
        previous_image = None
        if self.pk:
            previous_image = type(self).objects.filter(pk=self.pk).values_list(
                "image", flat=True
            ).first()

        super().save(*args, **kwargs)

        current_image = self.image.name
        if previous_image and previous_image != current_image:
            storage = self.image.storage
            transaction.on_commit(
                lambda name=previous_image, file_storage=storage: file_storage.delete(name)
            )

    def delete(self, *args, **kwargs):
        image_name = self.image.name if self.image else ""
        storage = self.image.storage
        result = super().delete(*args, **kwargs)
        if image_name:
            transaction.on_commit(
                lambda name=image_name, file_storage=storage: file_storage.delete(name)
            )
        return result


def validate_icon_identifier(value):
    """Legacy icon names are preserved; new values must be known identifiers."""
    if value and value not in KNOWN_ICONS:
        # Allow legacy values already stored in the database; they render with
        # a safe fallback icon. New/edited values are checked in the form.
        return


class ContactSubmission(models.Model):
    """Stored contact form messages, visible only to authorized staff."""

    name = models.CharField(max_length=120)
    phone_number = models.CharField(
        max_length=20,
        validators=[
            RegexValidator(
                regex=r"\A\+?[0-9][0-9\s().-]{5,19}\Z",
                message="Enter a valid phone number.",
            )
        ],
    )
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Contact submission"
        verbose_name_plural = "Contact submissions"

    def __str__(self):
        return f"{self.name} — {self.subject}"


class Exam(models.Model):
    """Exam announcements with multiple PDF attachments."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    title = models.CharField(
        max_length=255,
        help_text="Exam title (e.g., UPSC Civil Services 2026, SSC CGL 2026)."
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description or announcement details."
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        blank=True,
        help_text="Publication status: draft or published."
    )
    publish_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional scheduled publication date/time."
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional expiry date/time after which this is not publicly visible."
    )
    exam_date = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "Date of the exam or its main event. Drives the Upcoming Exams "
            "(today or later) and Recent Exams (before today) sections."
        ),
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    # Candidate date-of-birth window (inclusive boundaries). These are the
    # candidate's eligible DOB boundaries, not the exam's application dates.
    dob_start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Earliest eligible candidate date of birth (inclusive). This is a candidate DOB boundary, not the application opening date.",
    )
    dob_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Latest eligible candidate date of birth (inclusive). This is a candidate DOB boundary, not the application closing date.",
    )

    # Candidate qualifications accepted for this exam.
    eligible_qualifications = models.ManyToManyField(
        "jobs.Qualification",
        blank=True,
        related_name="exams",
        help_text="One or more qualifications accepted for this exam. A candidate qualifies if their qualification matches any selected option.",
    )

    text_styles = models.JSONField(
        blank=True,
        default=dict,
        help_text=(
            "Per-element presentation for this exam's title, description and "
            "link labels. Managed by the shared visual content editor."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "-created_at"]
        verbose_name = "Exam"
        verbose_name_plural = "Exams"
        indexes = [
            models.Index(fields=["status", "is_active"]),
            models.Index(fields=["publish_at", "expires_at"]),
        ]

    def __str__(self):
        return self.title

    @property
    def is_published(self):
        """Check if exam is currently visible to the public."""
        if self.status != self.Status.PUBLISHED or not self.is_active:
            return False
        from django.utils import timezone
        now = timezone.now()
        if self.publish_at and self.publish_at > now:
            return False
        if self.expires_at and self.expires_at <= now:
            return False
        return True

    @property
    def resource_urls(self):
        """Return all active ResourceURLs attached to this exam."""
        content_type = ContentType.objects.get_for_model(self.__class__)
        return ResourceURL.objects.filter(
            content_type=content_type,
            object_id=self.pk,
            is_active=True,
        ).order_by("sort_order", "pk")

    def clean(self):
        super().clean()
        if (
            self.dob_start_date
            and self.dob_end_date
            and self.dob_start_date > self.dob_end_date
        ):
            raise ValidationError(
                {
                    "dob_start_date": (
                        "DOB starting date cannot be later than the DOB ending date. "
                        "Set the earliest eligible date of birth on or before the latest one."
                    ),
                }
            )

    @property
    def has_dob_criteria(self):
        """Returns True if the exam has a configured candidate DOB window."""
        return self.dob_start_date is not None or self.dob_end_date is not None

    @property
    def dob_criteria_display(self):
        """Formatted candidate DOB window (inclusive)."""
        if self.dob_start_date and self.dob_end_date:
            start = self.dob_start_date.strftime("%d %b %Y")
            end = self.dob_end_date.strftime("%d %b %Y")
            if self.dob_start_date == self.dob_end_date:
                return f"Born on {start} only"
            return f"Born between {start} and {end} (both inclusive)"
        if self.dob_start_date:
            return f"Born on or after {self.dob_start_date.strftime('%d %b %Y')}"
        if self.dob_end_date:
            return f"Born on or before {self.dob_end_date.strftime('%d %b %Y')}"
        return "Not configured"

    @property
    def eligible_qualifications_display(self):
        """Comma-separated labels of the qualifications accepted for this exam."""
        names = [qualification.name for qualification in self.eligible_qualifications.all()]
        return ", ".join(names) if names else "Not configured"


class ExamPDF(models.Model):
    """PDF files attached to an exam."""

    exam = models.ForeignKey(
        Exam,
        related_name="pdfs",
        on_delete=models.CASCADE,
        help_text="Exam this PDF belongs to."
    )
    display_name = models.CharField(
        max_length=255,
        help_text="Human-readable name for this PDF (e.g., 'Official Notification', 'Syllabus PDF')."
    )
    pdf_file = models.FileField(
        upload_to="cms/exam_pdfs/",
        validators=[validate_content_pdf],
        help_text="PDF file only. Maximum size is configured with CMS_MAX_PDF_SIZE (default 20 MB)."
    )
    external_link = models.CharField(
        max_length=500,
        blank=True,
        validators=[validate_public_url],
        help_text="Optional external link (e.g., official download page)."
    )
    link_text = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional button text for the external link."
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    text_styles = models.JSONField(
        blank=True,
        default=dict,
        help_text=(
            "Per-element presentation for this PDF's download link label. "
            "Managed by the shared visual content editor."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "-created_at"]
        verbose_name = "Exam PDF"
        verbose_name_plural = "Exam PDFs"

    def __str__(self):
        return f"{self.display_name} ({self.exam.title})"

    def save(self, *args, **kwargs):
        previous_pdf = None
        if self.pk:
            previous_pdf = type(self).objects.filter(pk=self.pk).values_list(
                "pdf_file", flat=True
            ).first()

        super().save(*args, **kwargs)

        current_pdf = self.pdf_file.name
        if previous_pdf and previous_pdf != current_pdf:
            storage = self.pdf_file.storage
            transaction.on_commit(
                lambda name=previous_pdf, file_storage=storage: file_storage.delete(name)
            )

    def delete(self, *args, **kwargs):
        pdf_name = self.pdf_file.name if self.pdf_file else ""
        storage = self.pdf_file.storage
        result = super().delete(*args, **kwargs)
        if pdf_name:
            transaction.on_commit(
                lambda name=pdf_name, file_storage=storage: file_storage.delete(name)
            )
        return result


class ExamLink(models.Model):
    """A labelled URL attached to an exam.

    An exam can carry any number of links (registration page, official
    notification, download portal, and so on). Each link picks an icon type
    which is mapped to one of the site's built-in SVG icons, so the public
    template never hard-codes markup per link.
    """

    class IconType(models.TextChoices):
        REGISTRATION = "registration", "Registration / Apply online"
        NOTIFICATION = "notification", "Notification / Official notice"
        PDF = "pdf", "PDF / Document"
        WEBSITE = "website", "Official website"
        ADMIT_CARD = "admit_card", "Admit card"
        ANSWER_KEY = "answer_key", "Answer key"
        RESULT = "result", "Result"
        SYLLABUS = "syllabus", "Syllabus"
        EXTERNAL = "external", "External link"
        OTHER = "other", "Other"

    # Icon type -> identifier rendered by accounts/includes/portal_icon.html.
    ICON_NAMES = {
        IconType.REGISTRATION: "book",
        IconType.NOTIFICATION: "paper",
        IconType.PDF: "document",
        IconType.WEBSITE: "link",
        IconType.ADMIT_CARD: "ticket",
        IconType.ANSWER_KEY: "key",
        IconType.RESULT: "result",
        IconType.SYLLABUS: "book-open",
        IconType.EXTERNAL: "link",
    }

    exam = models.ForeignKey(
        Exam,
        related_name="links",
        on_delete=models.CASCADE,
        help_text="Exam this link belongs to.",
    )
    url = models.URLField(
        max_length=500,
        help_text="Destination URL (http/https), e.g. the official application or notification page.",
    )
    link_text = models.CharField(
        max_length=100,
        help_text="Visible label, e.g. 'Apply Online' or 'Download Notification'.",
    )
    icon_type = models.CharField(
        max_length=20,
        choices=IconType.choices,
        default=IconType.EXTERNAL,
        help_text="Icon shown next to the link on the public page.",
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = "Exam link"
        verbose_name_plural = "Exam links"

    def __str__(self):
        return f"{self.link_text} ({self.exam.title})"

    @property
    def icon_name(self):
        """Built-in icon identifier for this link's icon type."""
        return self.ICON_NAMES.get(self.icon_type, "link")


class ResourceURL(models.Model):
    """Generic URL attachment for exam-linked resources.

    Allows multiple URLs with custom labels and opening behavior to be attached
    to AnswerSheet, PreviousPaper, and other resource models. Each URL can have
    a display label (e.g., 'Download Notification', 'Apply Online'), can open
    in the same tab or a new tab, and supports sorting and activation.
    """

    class Target(models.TextChoices):
        SAME_TAB = "same", "Same tab"
        NEW_TAB = "new", "New tab"

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        limit_choices_to={"model__in": ["answersheet", "previouspaper", "registrationresource", "result"]},
        help_text="Model type this URL belongs to.",
    )
    object_id = models.PositiveIntegerField(
        help_text="Primary key of the object this URL belongs to.",
    )
    content_object = GenericForeignKey("content_type", "object_id")

    url = models.CharField(
        max_length=500,
        validators=[validate_public_url],
        help_text="Destination URL (http/https or internal path starting with /).",
    )
    label = models.CharField(
        max_length=100,
        help_text="Visible link text, e.g., 'Download Notification' or 'Apply Online'.",
    )
    target = models.CharField(
        max_length=10,
        choices=Target.choices,
        default=Target.NEW_TAB,
        help_text="Whether the link opens in the same tab or a new tab.",
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = "Resource URL"
        verbose_name_plural = "Resource URLs"
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.label}"


class PublishedExamResource(models.Model):
    """Shared behaviour for exam-linked resources with a publish state.

    Concrete models (answer sheets, registration resources, previous papers and
    results) reuse the same publication rules and PDF lifecycle: an item is only
    visible when it is published, active, and its publication date is not in the
    future. Replaced or removed PDF files are cleaned up only after the database
    transaction commits, so existing uploads are never lost on a failed save.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    title = models.CharField(max_length=255)
    description = models.TextField(
        blank=True,
        help_text="Optional description or instructions shown on the public page.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        help_text="Only published items appear on the public website.",
    )
    published_date = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "Date shown publicly. Leave empty to publish immediately, or set a "
            "future date to keep the item hidden until then."
        ),
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @property
    def is_published(self):
        """A resource is public only when published, active and dated due."""
        if self.status != self.Status.PUBLISHED or not self.is_active:
            return False
        if self.published_date and self.published_date > timezone.localdate():
            return False
        return True

    @property
    def display_date(self):
        """Publication date, falling back to the creation date."""
        if self.published_date:
            return self.published_date
        if self.created_at:
            return timezone.localtime(self.created_at).date()
        return None

    @property
    def resource_urls(self):
        """Return all active ResourceURLs for this resource instance."""
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(self.__class__)
        return ResourceURL.objects.filter(
            content_type=content_type,
            object_id=self.pk,
            is_active=True,
        ).order_by("sort_order", "pk")

    def save(self, *args, **kwargs):
        previous_pdf = None
        if self.pk:
            previous_pdf = type(self).objects.filter(pk=self.pk).values_list(
                "pdf_file", flat=True
            ).first()

        super().save(*args, **kwargs)

        current_pdf = self.pdf_file.name if self.pdf_file else ""
        if previous_pdf and previous_pdf != current_pdf:
            storage = self.pdf_file.storage
            transaction.on_commit(
                lambda name=previous_pdf, file_storage=storage: file_storage.delete(name)
            )

    def delete(self, *args, **kwargs):
        pdf_name = self.pdf_file.name if self.pdf_file else ""
        storage = self.pdf_file.storage if self.pdf_file else None
        result = super().delete(*args, **kwargs)
        if pdf_name and storage:
            transaction.on_commit(
                lambda name=pdf_name, file_storage=storage: file_storage.delete(name)
            )
        return result


class AnswerSheet(PublishedExamResource):
    """A downloadable answer-sheet PDF for an exam."""

    exam = models.ForeignKey(
        Exam,
        related_name="answer_sheets",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Optional exam this answer sheet belongs to.",
    )
    pdf_file = models.FileField(
        upload_to=SafePDFUploadTo("cms/answer_sheets/"),
        blank=True,
        validators=[validate_content_pdf],
        help_text="Answer-sheet PDF (optional). PDF only, maximum size configured with CMS_MAX_PDF_SIZE (default 20 MB).",
    )

    class Meta:
        ordering = ["sort_order", "-created_at"]
        verbose_name = "Answer sheet"
        verbose_name_plural = "Answer sheets"

    def __str__(self):
        return self.title


class RegistrationResource(PublishedExamResource):
    """A registration/application resource: a PDF, an official URL, or both."""

    exam = models.ForeignKey(
        Exam,
        related_name="registration_resources",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Optional exam this registration resource belongs to.",
    )
    pdf_file = models.FileField(
        upload_to=SafePDFUploadTo("cms/registration_forms/"),
        blank=True,
        validators=[validate_content_pdf],
        help_text="Optional registration/application form PDF. PDF only, maximum size configured with CMS_MAX_PDF_SIZE (default 20 MB).",
    )
    official_url = models.CharField(
        max_length=500,
        blank=True,
        validators=[validate_public_url],
        help_text="Optional official application URL (http/https).",
    )
    closing_date = models.DateField(
        null=True,
        blank=True,
        help_text="Optional last date to apply shown on the public page.",
    )

    class Meta:
        ordering = ["sort_order", "-created_at"]
        verbose_name = "Registration form"
        verbose_name_plural = "Registration forms"

    def __str__(self):
        return self.title


class PreviousPaper(PublishedExamResource):
    """A previous-year exam question paper (PDF required)."""

    exam = models.ForeignKey(
        Exam,
        related_name="previous_papers",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Optional exam this paper belongs to.",
    )
    exam_year = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Year the paper was held, e.g. 2025.",
    )
    pdf_file = models.FileField(
        upload_to=SafePDFUploadTo("cms/previous_papers/"),
        blank=True,
        validators=[validate_content_pdf],
        help_text="Paper PDF (optional). PDF only, maximum size configured with CMS_MAX_PDF_SIZE (default 20 MB).",
    )

    class Meta:
        ordering = ["sort_order", "-created_at"]
        verbose_name = "Previous paper"
        verbose_name_plural = "Previous papers"

    def __str__(self):
        return self.title


class Result(PublishedExamResource):
    """A result announcement with an official link and/or an optional PDF."""

    exam = models.ForeignKey(
        Exam,
        related_name="results",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Optional exam this result belongs to.",
    )
    official_url = models.CharField(
        max_length=500,
        blank=True,
        validators=[validate_public_url],
        help_text="Official result URL (http/https). Required unless a result PDF is uploaded.",
    )
    pdf_file = models.FileField(
        upload_to=SafePDFUploadTo("cms/results/"),
        blank=True,
        validators=[validate_content_pdf],
        help_text="Optional result PDF. PDF only, maximum size configured with CMS_MAX_PDF_SIZE (default 20 MB).",
    )

    class Meta:
        ordering = ["sort_order", "-created_at"]
        verbose_name = "Result"
        verbose_name_plural = "Results"

    def __str__(self):
        return self.title


class LatestJob(PublishedExamResource):
    """A latest job posting with an uploaded photo.

    Reuses the shared ``PublishedExamResource`` behaviour (title, description,
    publication status and date, display order, optional related exam, optional
    notification PDF, official URL, and the publish rules) and adds exactly one
    new content field: an uploaded photo shown on the public job card. The photo
    is validated by ``validate_content_image`` and is never stored inside a text
    field. A replaced or removed photo is deleted only after the database
    transaction commits, matching the PDF lifecycle of the other resources.
    """

    exam = models.ForeignKey(
        Exam,
        related_name="latest_jobs",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Optional exam or recruitment this job posting belongs to.",
    )
    official_url = models.CharField(
        max_length=500,
        blank=True,
        validators=[validate_public_url],
        help_text=(
            "Official job or notification URL (http/https). Required unless a "
            "notification PDF is uploaded."
        ),
    )
    pdf_file = models.FileField(
        upload_to=SafePDFUploadTo("cms/latest_jobs/"),
        blank=True,
        validators=[validate_content_pdf],
        help_text=(
            "Optional notification PDF. PDF only, maximum size configured with "
            "CMS_MAX_PDF_SIZE (default 20 MB)."
        ),
    )
    image = models.ImageField(
        upload_to="cms/latest_jobs/",
        blank=True,
        validators=[validate_content_image],
        error_messages={
            "invalid_image": "Upload a valid, uncorrupted PNG, JPG, JPEG, or WebP image."
        },
        help_text=(
            "Optional photo shown on the job card. PNG, JPG, JPEG, or WebP, "
            "maximum size configured with CMS_MAX_IMAGE_SIZE (default 5 MB)."
        ),
    )

    class Meta:
        ordering = ["sort_order", "-created_at"]
        verbose_name = "Latest job"
        verbose_name_plural = "Latest jobs"

    def save(self, *args, **kwargs):
        previous_image = None
        if self.pk:
            previous_image = type(self).objects.filter(pk=self.pk).values_list(
                "image", flat=True
            ).first()

        super().save(*args, **kwargs)

        current_image = self.image.name if self.image else ""
        if previous_image and previous_image != current_image:
            storage = self.image.storage
            transaction.on_commit(
                lambda name=previous_image, file_storage=storage: file_storage.delete(name)
            )

    def delete(self, *args, **kwargs):
        image_name = self.image.name if self.image else ""
        storage = self.image.storage if self.image else None
        result = super().delete(*args, **kwargs)
        if image_name and storage:
            transaction.on_commit(
                lambda name=image_name, file_storage=storage: file_storage.delete(name)
            )
        return result

    def __str__(self):
        return self.title
