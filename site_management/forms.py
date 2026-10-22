from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify

from .icons import ICON_CHOICES
from .models import (
    AnswerSheet,
    ContactSubmission,
    ContentItem,
    ContentLink,
    ContentSection,
    Exam,
    ExamPDF,
    LatestJob,
    PreviousPaper,
    RegistrationResource,
    ResourceURL,
    Result,
    SocialMediaProfile,
    WebsitePage,
    WebsiteSettings,
    validate_content_image,
    validate_content_pdf,
)

SECTION_SLUG_SUGGESTIONS = (
    ("jobs", "Latest jobs"),
    ("results", "Sarkari results"),
    ("admit-cards", "Admit cards"),
    ("answer-keys", "Answer keys"),
    ("admissions", "Admissions"),
    ("syllabus", "Syllabus"),
    ("previous-papers", "Previous papers"),
    ("updates", "Important updates"),
    ("announcements", "Announcements"),
    ("hero-actions", "Homepage hero buttons"),
    ("main-navigation", "Main navigation"),
    ("footer-quick-links", "Footer quick links"),
    ("footer-information", "Footer information"),
    ("footer-social", "Footer social links"),
    ("tools", "Tools landing page"),
)

LINK_FIELD_NAMES = {
    "url",
    "secondary_link_url",
    "button_url",
    "profile_url",
    "custom_icon_url",
    "icon_url",
    "logo_url",
    "favicon_url",
    "link_url",
    "contact_facebook_url",
    "contact_instagram_url",
    "contact_whatsapp_url",
}


def add_link_test_attributes(fields):
    for field_name, field in fields.items():
        if field_name in LINK_FIELD_NAMES or field_name.endswith("_url"):
            field.widget.attrs["data-test-link"] = "true"
            field.widget.attrs["inputmode"] = "url"


class IconPickerWidget(forms.Select):
    """Visual icon selector; JS enhances it into a searchable grid with previews."""

    template_name = "site_management/widgets/icon_picker.html"

    class Media:
        js = ("site_management/management_icon_picker.js",)
        css = {"all": ("site_management/management_icon_picker.css",)}


class ManagementForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} management-input".strip()
        add_link_test_attributes(self.fields)


class ManagementUserEditForm(ManagementForm):
    """Edit the safe profile fields of an existing account.

    Only the display name, email address, and eligibility profile details are
    exposed. Passwords are never read or written here, and staff/superuser
    privileges are handled by dedicated, permission-checked workspace actions
    rather than this form.
    """

    class Meta:
        model = get_user_model()
        fields = ["full_name", "email", "date_of_birth", "qualification"]
        labels = {
            "full_name": "Full name",
            "email": "Email address",
            "date_of_birth": "Date of birth",
            "qualification": "Highest qualification",
        }
        help_texts = {
            "full_name": "Display name shown in the workspace and on the public website.",
            "email": "Used for sign-in and notifications. Must stay unique to this account.",
            "date_of_birth": "Used by the exam eligibility checker for date-of-birth windows.",
            "qualification": "Used by the exam eligibility checker to match accepted qualifications.",
        }
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().casefold()
        duplicates = get_user_model().objects.filter(email__iexact=email)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError(
                "Another account already uses this email address."
            )
        return email


class WebsiteSettingsForm(ManagementForm):
    class Meta:
        model = WebsiteSettings
        exclude = ["updated_at"]
        help_texts = {
            "site_name": "Header and footer brand name, page titles, and browser tab title.",
            "tagline": "Short brand line beside the logo in the public header and footer.",
            "logo_text": "Fallback brand mark shown in the public header and footer when no logo image is set.",
            "logo_url": "Optional public logo image URL used in the header and footer.",
            "favicon_url": "Optional browser-tab icon URL.",
            "header_text": "Small eyebrow above the homepage hero title.",
            "hero_title": "Main heading in the homepage hero.",
            "hero_description": "Homepage hero introduction and search-page description.",
            "announcement": "Single compact announcement shown directly under the homepage hero copy.",
            "hero_note_title": "Heading for the editorial note displayed with homepage content.",
            "hero_note_body": "Body text for the editorial note displayed with homepage content.",
            "hero_note_footer": "Closing note shown in the editorial panel on the homepage.",
            "footer_description": "Brand introduction in the public-site footer.",
            "footer_contact": "Contact summary used in the public-site footer where configured.",
            "footer_copyright": "Name shown in the public footer copyright line.",
            "footer_disclaimer": "Site disclaimer text shown with the footer information.",
        }
        widgets = {
            "hero_description": forms.Textarea(attrs={"rows": 3}),
            "hero_note_body": forms.Textarea(attrs={"rows": 3}),
            "footer_description": forms.Textarea(attrs={"rows": 3}),
            "footer_contact": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.field_groups = []
        for title, names in (
            ("Brand identity", ("site_name", "tagline", "logo_text", "logo_url", "favicon_url")),
            ("Homepage hero", ("header_text", "hero_title", "hero_description", "announcement")),
            ("Homepage editorial note", ("hero_note_title", "hero_note_body", "hero_note_footer")),
            ("Public footer", ("footer_description", "footer_contact", "footer_copyright", "footer_disclaimer")),
        ):
            fields = [self[name] for name in names if name in self.fields]
            if fields:
                self.field_groups.append((title, fields))


class ContentSectionForm(ManagementForm):
    icon = forms.ChoiceField(
        choices=(("", "---------"), *ICON_CHOICES),
        required=False,
        widget=IconPickerWidget,
    )

    class Meta:
        model = ContentSection
        fields = [
            "area",
            "title",
            "slug",
            "description",
            "icon",
            "sort_order",
            "is_active",
        ]
        help_texts = {
            "area": "Select the precise public area where this section and its content will appear.",
            "title": "Heading shown for this section on the selected public area.",
            "slug": "Stable internal identifier used by the existing public section route; do not change after publishing without updating inbound links.",
            "description": "Supporting text shown next to the section heading in its public area.",
            "icon": "Optional icon used by public layouts that display this section's visual marker.",
            "sort_order": "Position among sections in this area (lower values appear first).",
            "is_active": "Inactive sections and their content are hidden from the public site.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.required = (name == "title")
        sections = ContentSection.objects.all()
        if self.instance.pk:
            sections = sections.exclude(pk=self.instance.pk)
        used_slugs = set(sections.values_list("slug", flat=True))
        self.slug_suggestions = [
            (slug, label)
            for slug, label in SECTION_SLUG_SUGGESTIONS
            if slug not in used_slugs or slug == self.instance.slug
        ]
        self.fields["slug"].label = "Section slug"
        self.fields["slug"].help_text = (
            "Choose a suggested section key or enter a custom slug. Existing public "
            "links use this value, so changing it after publishing can break those links."
        )
        self.fields["slug"].widget.attrs.update(
            {
                "list": "management-section-slugs",
                "placeholder": "Select a suggestion or enter a custom slug",
            }
        )
        current_icon = self.instance.icon
        if current_icon and current_icon not in dict(ICON_CHOICES):
            self.fields["icon"].choices = [
                *self.fields["icon"].choices,
                (current_icon, f"Legacy icon: {current_icon}"),
            ]

    def clean_icon(self):
        icon = self.cleaned_data.get("icon", "")
        if icon and icon not in dict(ICON_CHOICES):
            if self.instance and self.instance.pk and self.instance.icon == icon:
                return icon
            raise forms.ValidationError(
                "Select an icon from the picker or leave it empty."
            )
        return icon

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("slug"):
            cleaned["slug"] = slugify(cleaned.get("title", ""))[:100] or "section"
        if not cleaned.get("area"):
            cleaned["area"] = getattr(self.instance, "area", "") or ContentSection.Area.HOMEPAGE
        if cleaned.get("area") == ContentSection.Area.TOOLS:
            existing_tools_area = ContentSection.objects.filter(
                area=ContentSection.Area.TOOLS
            )
            if self.instance.pk:
                existing_tools_area = existing_tools_area.exclude(pk=self.instance.pk)
            if existing_tools_area.exists():
                self.add_error(
                    "area",
                    "The Tools landing page uses one section for its heading, introduction, and tool cards. Edit the existing Tools section instead.",
                )
        return cleaned


class ContentItemForm(ManagementForm):
    icon = forms.ChoiceField(
        choices=(("", "---------"), *ICON_CHOICES),
        required=False,
        widget=IconPickerWidget,
    )
    image = forms.ImageField(
        required=False,
        validators=[validate_content_image],
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
            }
        ),
        error_messages={
            "invalid_image": "Upload a valid, uncorrupted PNG, JPG, JPEG, or WebP image.",
        },
    )
    secondary_image = forms.ImageField(
        required=False,
        validators=[validate_content_image],
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
            }
        ),
        error_messages={
            "invalid_image": "Upload a valid, uncorrupted PNG, JPG, JPEG, or WebP image."
        },
    )
    thumbnail_image = forms.ImageField(
        required=False,
        validators=[validate_content_image],
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
            }
        ),
        error_messages={
            "invalid_image": "Upload a valid, uncorrupted PNG, JPG, JPEG, or WebP image."
        },
    )
    pdf_file = forms.FileField(
        required=False,
        label="PDF file (optional)",
        validators=[validate_content_pdf],
        widget=forms.ClearableFileInput(
            attrs={"accept": ".pdf,application/pdf"}
        ),
    )

    def __init__(self, *args, section, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.section = section
        self.section = section
        current_icon = self.instance.icon
        if current_icon and current_icon not in dict(ICON_CHOICES):
            self.fields["icon"].choices = [
                *self.fields["icon"].choices,
                (current_icon, f"Legacy icon: {current_icon}"),
            ]
        self.fields["parent"].queryset = ContentItem.objects.filter(
            section=section,
            parent__isnull=True,
        ).exclude(pk=self.instance.pk)
        self.fields["parent"].required = False
        if section.area != ContentSection.Area.HOMEPAGE:
            for field_name in (
                "pdf_file",
                "subtitle",
                "short_description",
                "additional_description",
                "badge_text",
                "eyebrow_text",
                "highlight_text",
                "caption",
                "source_name",
                "published_at",
                "primary_link_text",
                "secondary_link_text",
                "secondary_link_url",
                "button_text",
                "button_url",
                "call_to_action",
                "link_title",
                "accessible_label",
                "image",
                "secondary_image",
                "thumbnail_image",
                "image_alt",
                "image_caption",
                "image_position",
                "image_alignment",
                "image_size",
                "image_fit",
                "block_type",
                "background_color",
                "text_color",
                "border_color",
                "border_radius",
                "spacing",
                "content_alignment",
                "layout",
                "badge_color",
                "custom_css_class",
                "show_on_desktop",
                "show_on_tablet",
                "show_on_mobile",
                "is_featured",
                "show_on_homepage",
                "publish_at",
                "expires_at",
                "internal_notes",
            ):
                if section.area == ContentSection.Area.TOOLS and field_name in {
                    "image",
                    "thumbnail_image",
                }:
                    continue
                self.fields.pop(field_name, None)

        for fname, field in self.fields.items():
            field.required = (fname == "label")

        self.fields["body"].label = "Description"
        self.fields["body"].help_text = "Main description (optional)."
        self.fields["label"].required = True
        self.fields["url"].required = False
        self.fields["label"].widget.attrs["placeholder"] = "Block title (required)"
        self.fields["body"].widget.attrs["placeholder"] = "Write the main description (optional)"
        self.fields["url"].label = "Primary link URL"
        self.fields["url"].widget.attrs["placeholder"] = "https://example.org/page or /local/path/"
        for field_name, location in {
            "label": "Content block heading or the visible navigation/footer link label.",
            "title_color": "Homepage content card and detail-page title text.",
            "title_background_color": "Background behind this block title on homepage cards and its detail page.",
            "subtitle": "Secondary heading shown below the title on homepage cards and detail pages.",
            "subtitle_color": "Subtitle text on homepage cards and detail pages.",
            "subtitle_background_color": "Background behind the subtitle on homepage cards and detail pages.",
            "url": "Primary destination for this item in its public section or menu.",
            "icon": "Icon displayed with this block or menu item where the public layout supports it.",
            "sort_order": "Display position among items in this section (lower values appear first).",
            "is_active": "Controls whether this item appears in the public section.",
            "show_on_homepage": "Eligible for homepage box. (Note: Only the 2 newest active items in this section appear directly on the homepage; all items remain accessible in the section archive).",
            "is_featured": "Highlighted visually in listings where the template supports featured cards.",
            "publish_at": "Optional future date/time to begin displaying this item publicly.",
            "expires_at": "Optional future date/time after which this item is automatically hidden.",
            "internal_notes": "Private notes for editorial staff; never shown on the public website.",
        }.items():
            if field_name in self.fields:
                self.fields[field_name].help_text = location
        if "show_on_homepage" in self.fields:
            self.fields["show_on_homepage"].label = "Display on homepage"
        if "subtitle" in self.fields:
            self.fields["subtitle"].widget.attrs["placeholder"] = "Optional subtitle or secondary heading"
        if "short_description" in self.fields:
            self.fields["short_description"].widget.attrs["placeholder"] = "Brief summary for listings"
        if "additional_description" in self.fields:
            self.fields["additional_description"].widget.attrs["placeholder"] = "Extended information or instructions"
        if "badge_text" in self.fields:
            self.fields["badge_text"].widget.attrs["placeholder"] = "e.g. NEW, UPDATE, ACTIVE"
        if "eyebrow_text" in self.fields:
            self.fields["eyebrow_text"].widget.attrs["placeholder"] = "e.g. EXAM NOTICE 2026"
        if "highlight_text" in self.fields:
            self.fields["highlight_text"].widget.attrs["placeholder"] = "e.g. Last date extended"
        if "caption" in self.fields:
            self.fields["caption"].widget.attrs["placeholder"] = "Optional explanatory caption"
        if "source_name" in self.fields:
            self.fields["source_name"].widget.attrs["placeholder"] = "e.g. Official Commission / Board"
        if "primary_link_text" in self.fields:
            self.fields["primary_link_text"].widget.attrs["placeholder"] = "e.g. View Details"
        if "secondary_link_url" in self.fields:
            self.fields["secondary_link_url"].widget.attrs["placeholder"] = "https://example.org/related"
        if "secondary_link_text" in self.fields:
            self.fields["secondary_link_text"].widget.attrs["placeholder"] = "e.g. Official Notification"
        if "button_text" in self.fields:
            self.fields["button_text"].label = "Button label"
            self.fields["button_text"].widget.attrs["placeholder"] = "e.g. Apply Now"
        if "button_url" in self.fields:
            self.fields["button_url"].label = "Button destination URL"
            self.fields["button_url"].widget.attrs["placeholder"] = "https://example.org/apply"
        if "call_to_action" in self.fields:
            self.fields["call_to_action"].widget.attrs["placeholder"] = "e.g. Complete form before deadline"
        if "link_title" in self.fields:
            self.fields["link_title"].widget.attrs["placeholder"] = "Link hover tooltip"
        if "accessible_label" in self.fields:
            self.fields["accessible_label"].widget.attrs["placeholder"] = "Screen reader label"
        if "custom_css_class" in self.fields:
            self.fields["custom_css_class"].widget.attrs["placeholder"] = "content-card featured"
        if "internal_notes" in self.fields:
            self.fields["internal_notes"].widget.attrs["placeholder"] = "Administrator notes (internal use only)"

        if section.area == ContentSection.Area.TOOLS:
            tool_paths = (
                ("/tools/image-resizer/", "Image Resizer"),
                ("/tools/jpg-to-pdf/", "JPG to PDF Converter"),
                ("/tools/photo-name-date/", "Photo Name & Date Maker"),
                ("/tools/photo-signature-joiner/", "Photo Signature Joiner"),
                ("/tools/resume-cv-photo/", "Resume/CV Photo Tool"),
            )
            choices = [("", "Select a built-in tool destination")]
            choices.extend(tool_paths)
            current_url = getattr(self.instance, "url", "")
            if current_url and current_url not in dict(tool_paths):
                choices.append((current_url, f"Existing destination: {current_url}"))
            self.fields["url"] = forms.ChoiceField(
                choices=choices,
                required=True,
                label="Built-in tool destination",
                help_text="Select the fixed route for the existing tool. Tool processing and client-side behavior remain unchanged.",
                widget=forms.Select(attrs={"class": "management-input"}),
            )
            allowed_fields = {
                "label", "body", "url", "icon", "image", "thumbnail_image",
                "sort_order", "is_active",
            }
            for field_name in list(self.fields):
                if field_name not in allowed_fields:
                    self.fields.pop(field_name)
            self.fields["label"].required = True
            self.fields["label"].help_text = "Tool card title shown on the public Tools landing page."
            self.fields["body"].required = True
            self.fields["body"].label = "Tool card description"
            self.fields["body"].help_text = "Short explanation shown under this tool title."
            self.fields["icon"].help_text = "Optional icon displayed in the public tool card."
            self.fields["image"].help_text = "Optional image for the public tool card; leave blank to use its icon."
            self.fields["thumbnail_image"].help_text = "Optional small image for the public tool card."
            self.fields["sort_order"].help_text = "Card order on the Tools landing page (lower values appear first)."
            self.fields["is_active"].help_text = "Inactive cards are hidden from the public Tools landing page."

        self.field_groups = []
        location_prefix = (
            f"Public location: {section.get_area_display()} → {section.title}. "
        )
        for field_name, field in self.fields.items():
            field_label = field.label or field_name.replace("_", " ")
            detail = field.help_text or f"Controls this content block's {field_label.lower()}."
            if not detail.startswith("Public location:"):
                field.help_text = location_prefix + detail
        groups = (
            (
                "Essential Content",
                (
                    "label",
                    "subtitle",
                    "body",
                    "pdf_file",
                    "url",
                    "primary_link_text",
                    "published_at",
                    "source_name",
                    "is_active",
                    "sort_order",
                    "parent",
                ),
            ),
            (
                "Card Media & Icon",
                (
                    "icon",
                    "image",
                    "image_alt",
                    "image_caption",
                ),
            ),
            (
                "Action Buttons & Extra Links",
                (
                    "button_text",
                    "button_url",
                    "secondary_link_text",
                    "secondary_link_url",
                    "open_new_tab",
                    "call_to_action",
                ),
            ),
            (
                "Badges & Highlights",
                (
                    "badge_text",
                    "badge_color",
                    "eyebrow_text",
                    "highlight_text",
                ),
            ),
            (
                "Publishing & Scheduling",
                (
                    "show_on_homepage",
                    "is_featured",
                    "publish_at",
                    "expires_at",
                    "internal_notes",
                ),
            ),
            (
                "Advanced Settings & Styling (Optional)",
                (
                    "title_color",
                    "title_background_color",
                    "subtitle_color",
                    "subtitle_background_color",
                    "background_color",
                    "text_color",
                    "border_color",
                    "block_type",
                    "layout",
                    "spacing",
                    "border_radius",
                    "content_alignment",
                    "image_position",
                    "image_alignment",
                    "image_size",
                    "image_fit",
                    "secondary_image",
                    "thumbnail_image",
                    "custom_css_class",
                    "show_on_desktop",
                    "show_on_tablet",
                    "show_on_mobile",
                    "link_title",
                    "accessible_label",
                    "style",
                    "short_description",
                    "additional_description",
                    "caption",
                ),
            ),
        )
        for group_title, field_names in groups:
            bound_fields = [
                self[name] for name in field_names if name in self.fields
            ]
            if bound_fields:
                self.field_groups.append((group_title, bound_fields))

    class Meta:
        model = ContentItem
        fields = [
            "parent",
            "label",
            "title_color",
            "title_background_color",
            "body",
            "subtitle",
            "subtitle_color",
            "subtitle_background_color",
            "short_description",
            "additional_description",
            "badge_text",
            "eyebrow_text",
            "highlight_text",
            "caption",
            "source_name",
            "published_at",
            "primary_link_text",
            "secondary_link_text",
            "secondary_link_url",
            "button_text",
            "button_url",
            "call_to_action",
            "link_title",
            "accessible_label",
            "image",
            "secondary_image",
            "thumbnail_image",
            "image_alt",
            "image_caption",
            "image_position",
            "image_alignment",
            "image_size",
            "image_fit",
            "url",
            "style",
            "icon",
            "block_type",
            "background_color",
            "text_color",
            "border_color",
            "border_radius",
            "spacing",
            "content_alignment",
            "layout",
            "badge_color",
            "custom_css_class",
            "show_on_desktop",
            "show_on_tablet",
            "show_on_mobile",
            "is_featured",
            "show_on_homepage",
            "publish_at",
            "expires_at",
            "internal_notes",
            "sort_order",
            "open_new_tab",
            "is_active",
            "pdf_file",
        ]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 4}),
            "short_description": forms.Textarea(attrs={"rows": 2}),
            "additional_description": forms.Textarea(attrs={"rows": 3}),
            "internal_notes": forms.Textarea(attrs={"rows": 2}),
            "icon": IconPickerWidget,
        }

    def clean_icon(self):
        icon = self.cleaned_data.get("icon", "")
        if icon and icon not in dict(ICON_CHOICES):
            # Preserve legacy stored values; reject unknown new text entries.
            if self.instance and self.instance.pk and self.instance.icon == icon:
                return icon
            raise forms.ValidationError(
                "Select an icon from the picker or leave it empty."
            )
        return icon


class WebsitePageForm(forms.ModelForm):
    """CMS form for editing website pages (About/Contact/Privacy/Details)."""

    image = forms.ImageField(
        required=False,
        validators=[validate_content_image],
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
            }
        ),
        error_messages={
            "invalid_image": "Upload a valid, uncorrupted PNG, JPG, JPEG, or WebP image.",
        },
    )

    class Meta:
        model = WebsitePage
        fields = [
            "title",
            "subtitle",
            "description",
            "image",
            "image_alt",
            "image_caption",
            "link_url",
            "link_text",
            "contact_email",
            "contact_phone",
            "contact_address",
            "contact_hours",
            "contact_intro",
            "contact_facebook_url",
            "contact_instagram_url",
            "contact_whatsapp_url",
            "is_published",
        ]
        help_texts = {
            "title": "Heading shown at the top of this public information page.",
            "subtitle": "Optional subheading directly below the page title.",
            "description": "Main page content shown on the selected public route.",
            "image": "Optional image shown on this page only.",
            "image_alt": "Alternative text for the optional page image.",
            "image_caption": "Optional caption below the page image.",
            "link_url": "Optional destination linked from this page.",
            "link_text": "Visible label for the optional page link.",
            "contact_email": "Contact page only: public email address.",
            "contact_phone": "Contact page only: public phone number.",
            "contact_address": "Contact page only: public mailing address.",
            "contact_hours": "Contact page only: public office hours.",
            "contact_intro": "Contact page only: introduction above the message form.",
            "contact_facebook_url": "Contact page only: optional Facebook profile link.",
            "contact_instagram_url": "Contact page only: optional Instagram profile link.",
            "contact_whatsapp_url": "Contact page only: optional WhatsApp contact link.",
            "is_published": "When off, the corresponding public route returns the existing unavailable-page response.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 8}),
            "contact_intro": forms.Textarea(attrs={"rows": 3}),
            "contact_address": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.required = (name == "title")
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "management-input")
        add_link_test_attributes(self.fields)
        self.fields["link_url"].widget.attrs["placeholder"] = (
            "https://example.org/page or /local/path/"
        )
        self.fields["contact_whatsapp_url"].widget.attrs["placeholder"] = (
            "https://wa.me/919XXXXXXXXX"
        )
        self.fields["contact_facebook_url"].widget.attrs["placeholder"] = (
            "https://facebook.com/your-page"
        )
        self.fields["contact_instagram_url"].widget.attrs["placeholder"] = (
            "https://instagram.com/your-profile"
        )
        self.fields["title"].label = "Page Title"
        self.fields["title"].help_text = "Main heading displayed at the top of the page."
        self.fields["subtitle"].label = "Page Subtitle"
        self.fields["subtitle"].help_text = "Optional brief line shown directly underneath the title."
        self.fields["description"].label = "Page Content"
        self.fields["description"].help_text = "The complete text of your page (supports text formatting and paragraphs)."
        self.fields["is_published"].label = "Publish Page Live"
        self.fields["is_published"].help_text = "When checked, this page is immediately visible to public visitors. When unchecked, visitors see an 'Unavailable' notice."

        contact_field_names = (
            "contact_email",
            "contact_phone",
            "contact_address",
            "contact_hours",
            "contact_intro",
            "contact_facebook_url",
            "contact_instagram_url",
            "contact_whatsapp_url",
        )
        is_contact_page = (
            (self.instance and self.instance.pk and self.instance.page_type == WebsitePage.PageType.CONTACT_US)
            or (not (self.instance and self.instance.pk))  # creation form
        )
        if not is_contact_page:
            for cfield in contact_field_names:
                self.fields.pop(cfield, None)
        else:
            if "contact_email" in self.fields:
                self.fields["contact_email"].label = "Public Support Email"
                self.fields["contact_email"].help_text = "Contact page only: email address visitors can write to."
            if "contact_phone" in self.fields:
                self.fields["contact_phone"].label = "Public Helpline Phone"
                self.fields["contact_phone"].help_text = "Contact page only: phone number shown on the contact page."
            if "contact_address" in self.fields:
                self.fields["contact_address"].label = "Office Address"
                self.fields["contact_address"].help_text = "Contact page only: postal address."
            if "contact_hours" in self.fields:
                self.fields["contact_hours"].label = "Office Hours"
                self.fields["contact_hours"].help_text = "Contact page only: e.g. Mon–Fri, 9:30 AM – 5:30 PM IST."
            if "contact_intro" in self.fields:
                self.fields["contact_intro"].label = "Message Form Instructions"
                self.fields["contact_intro"].help_text = "Contact page only: welcome note displayed above the contact form."
            if "contact_facebook_url" in self.fields:
                self.fields["contact_facebook_url"].label = "Facebook Profile URL"
            if "contact_instagram_url" in self.fields:
                self.fields["contact_instagram_url"].label = "Instagram Profile URL"
            if "contact_whatsapp_url" in self.fields:
                self.fields["contact_whatsapp_url"].label = "WhatsApp Contact Link"

        content_fields = ("title", "subtitle", "description", "is_published")
        field_groups = []
        if "page_type" in self.fields:
            field_groups.append(("Page Setup", ("page_type", *content_fields)))
        else:
            field_groups.append(("Page Content", content_fields))

        field_groups.append(("Page Image & Media (Optional)", ("image", "image_alt", "image_caption")))
        field_groups.append(("Optional Action Link", ("link_url", "link_text")))

        if is_contact_page:
            field_groups.append((
                "Contact Information (Contact Us Page Only)",
                contact_field_names,
            ))

        self.field_groups = [
            (title, [self[name] for name in names if name in self.fields])
            for title, names in field_groups
            if any(name in self.fields for name in names)
        ]

    def clean(self):
        return super().clean()


class WebsitePageCreateForm(WebsitePageForm):
    page_type = forms.ChoiceField(
        choices=(("", "Select a public page"), *WebsitePage.PageType.choices),
        help_text="Choose an existing public route to add editable page content to.",
    )

    class Meta(WebsitePageForm.Meta):
        fields = ["page_type", *WebsitePageForm.Meta.fields]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["page_type"].required = False
        existing_types = set(WebsitePage.objects.values_list("page_type", flat=True))
        self.fields["page_type"].choices = [
            ("", "Select a public page"),
            *(
                choice
                for choice in WebsitePage.PageType.choices
                if choice[0] not in existing_types
            ),
        ]
        self.fields["page_type"].widget.attrs["class"] = "management-input"

    def clean_page_type(self):
        page_type = self.cleaned_data.get("page_type")
        if not page_type:
            existing_types = set(WebsitePage.objects.values_list("page_type", flat=True))
            for choice in WebsitePage.PageType.choices:
                if choice[0] not in existing_types:
                    return choice[0]
            raise forms.ValidationError("All supported public pages are already configured.")
        if WebsitePage.objects.filter(page_type=page_type).exists():
            raise forms.ValidationError("This public page is already configured.")
        return page_type


class ContentLinkForm(forms.ModelForm):
    content_item = forms.ModelChoiceField(
        queryset=ContentItem.objects.none(),
        label="Parent content item",
        help_text="The CMS block this additional link belongs to. Only top-level blocks can own links.",
    )
    icon = forms.ChoiceField(
        choices=(("", "No built-in icon"), *ICON_CHOICES),
        required=False,
        widget=IconPickerWidget,
    )
    starts_at = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )
    ends_at = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )

    class Meta:
        model = ContentLink
        fields = [
            "content_item",
            "label",
            "url",
            "description",
            "icon",
            "icon_url",
            "icon_color",
            "is_active",
            "open_new_tab",
            "display_order",
            "starts_at",
            "ends_at",
        ]
        help_texts = {
            "label": "Link text displayed beside the parent block on its public page.",
            "url": "Local path or HTTP/HTTPS destination for this link.",
            "description": "Optional supporting text shown with this link where the public layout supports it.",
            "icon_url": "Optional custom icon image URL. If supplied, it is used instead of the built-in icon.",
            "icon_color": "Optional six-digit HEX color applied to the built-in icon.",
            "is_active": "Inactive links are hidden from public pages.",
            "open_new_tab": "Open this public link in a new browser tab.",
            "display_order": "Order among extra links attached to the parent block (lower values first).",
            "starts_at": "Optional start time; the link stays hidden before this time.",
            "ends_at": "Optional end time; the link is hidden at and after this time.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        public_link_areas = [
            ContentSection.Area.NAVIGATION,
            ContentSection.Area.HOMEPAGE,
            ContentSection.Area.ANNOUNCEMENTS,
            ContentSection.Area.HERO_ACTIONS,
            ContentSection.Area.FOOTER,
        ]
        queryset = ContentItem.objects.filter(
            parent__isnull=True,
            section__area__in=public_link_areas,
        ).select_related("section").order_by(
            "section__area", "section__sort_order", "sort_order", "pk"
        )
        self.fields["content_item"].queryset = queryset
        self.fields["content_item"].label_from_instance = (
            lambda item: item.location_path
        )
        current_icon = self.instance.icon
        if current_icon and current_icon not in dict(ICON_CHOICES):
            self.fields["icon"].choices = [
                *self.fields["icon"].choices,
                (current_icon, f"Legacy icon: {current_icon}"),
            ]
        for field_name, field in self.fields.items():
            field_label = field.label or field_name.replace("_", " ")
            detail = field.help_text or f"Controls the public {field_label.lower()}."
            field.help_text = (
                "Public location: the selected parent content block. " + detail
            )
        add_link_test_attributes(self.fields)

    def clean(self):
        cleaned = super().clean()
        starts_at = cleaned.get("starts_at")
        ends_at = cleaned.get("ends_at")
        if starts_at and ends_at and ends_at <= starts_at:
            self.add_error("ends_at", "End date must be later than the start date.")
        return cleaned

    def clean_icon(self):
        icon = self.cleaned_data.get("icon", "")
        if icon and icon not in dict(ICON_CHOICES):
            if self.instance and self.instance.pk and self.instance.icon == icon:
                return icon
            raise forms.ValidationError("Select an icon from the picker or leave it empty.")
        return icon


class SocialMediaProfileForm(forms.ModelForm):
    built_in_icon = forms.ChoiceField(
        choices=(("", "Use platform initial"), *ICON_CHOICES),
        required=False,
        widget=IconPickerWidget,
        help_text="Optional built-in icon shown when a custom icon URL is not set.",
    )

    class Meta:
        model = SocialMediaProfile
        fields = [
            "platform",
            "profile_url",
            "custom_icon_url",
            "built_in_icon",
            "icon_color",
            "accessible_label",
            "display_location",
            "is_active",
            "display_order",
        ]
        help_texts = {
            "platform": "Unique social platform profile configured for the public header/footer.",
            "profile_url": "Public profile, channel, or WhatsApp URL.",
            "custom_icon_url": "Optional custom image URL; takes precedence over the built-in icon.",
            "icon_color": "Optional six-digit HEX color applied to the built-in icon or initial.",
            "accessible_label": "Optional accessible name announced by screen readers.",
            "display_location": "Choose whether this profile appears in the public header, footer, or both.",
            "is_active": "Inactive profiles are hidden from the public header and footer.",
            "display_order": "Order of this profile relative to other social links.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        existing_profiles = SocialMediaProfile.objects.all()
        if self.instance.pk:
            existing_profiles = existing_profiles.exclude(pk=self.instance.pk)
        existing_platforms = set(
            existing_profiles.values_list("platform", flat=True)
        )
        self.fields["platform"].choices = [
            choice
            for choice in SocialMediaProfile.Platform.choices
            if choice[0] not in existing_platforms
        ]
        current_icon = self.instance.built_in_icon
        if current_icon and current_icon not in dict(ICON_CHOICES):
            self.fields["built_in_icon"].choices = [
                *self.fields["built_in_icon"].choices,
                (current_icon, f"Legacy icon: {current_icon}"),
            ]
        for field_name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "management-input")
            field_label = field.label or field_name.replace("_", " ")
            detail = field.help_text or f"Controls this public profile's {field_label.lower()}."
            field.help_text = (
                "Public location: the selected header/footer placement on all public pages. "
                + detail
            )
        add_link_test_attributes(self.fields)

    def clean_platform(self):
        platform = self.cleaned_data.get("platform")
        if platform and platform not in dict(SocialMediaProfile.Platform.choices):
            raise forms.ValidationError("Select a supported social platform.")
        return platform

    def clean_built_in_icon(self):
        icon = self.cleaned_data.get("built_in_icon", "")
        if icon and icon not in dict(ICON_CHOICES):
            if self.instance and self.instance.pk and self.instance.built_in_icon == icon:
                return icon
            raise forms.ValidationError("Select an icon from the picker or leave it empty.")
        return icon


class ContactMessageForm(forms.ModelForm):
    """Public contact form; validated server-side and stored for staff review."""

    class Meta:
        model = ContactSubmission
        fields = ["name", "phone_number", "email", "subject", "message"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "contact-input",
                "placeholder": "Your full name",
                "autocomplete": "name",
            }),
            "phone_number": forms.TextInput(attrs={
                "class": "contact-input",
                "placeholder": "+91 98765 43210",
                "autocomplete": "tel",
                "inputmode": "tel",
            }),
            "email": forms.EmailInput(attrs={
                "class": "contact-input",
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }),
            "subject": forms.TextInput(attrs={
                "class": "contact-input",
                "placeholder": "Brief subject (e.g. Wrong exam date for SSC CGL)",
            }),
            "message": forms.Textarea(attrs={
                "class": "contact-input",
                "rows": 5,
                "placeholder": "Describe your question, correction, or suggestion in detail…",
            }),
        }

    # Honeypot field: real users never fill this in.
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "portal-honeypot",
                "tabindex": "-1",
                "autocomplete": "off",
                "aria-hidden": "true",
            }
        ),
        label="Leave this field empty",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("website"):
            raise forms.ValidationError("This form could not be submitted.")
        return cleaned

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Enter your name.")
        return name

    def clean_phone_number(self):
        phone_number = (self.cleaned_data.get("phone_number") or "").strip()
        digit_count = sum(character.isdigit() for character in phone_number)
        if not 7 <= digit_count <= 15:
            raise forms.ValidationError(
                "Enter a phone number containing 7 to 15 digits."
            )
        return phone_number

    def clean_subject(self):
        subject = (self.cleaned_data.get("subject") or "").strip()
        if not subject:
            raise forms.ValidationError("Enter a subject.")
        return subject

    def clean_message(self):
        message = (self.cleaned_data.get("message") or "").strip()
        if len(message) < 10:
            raise forms.ValidationError("Please write a message of at least 10 characters.")
        if len(message) > 5000:
            raise forms.ValidationError("Please keep your message under 5,000 characters.")
        if message.count("http") > 5:
            raise forms.ValidationError("Your message looks like spam; please remove some links.")
        return message


PUBLIC_EXAM_LOCATION = (
    "Public location: the Exams page and the Exams box on the homepage. "
)


class ExamForm(ManagementForm):
    """Create or edit an exam announcement from the workspace."""

    publish_at = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )
    expires_at = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )

    class Meta:
        model = Exam
        fields = [
            "title",
            "description",
            "status",
            "publish_at",
            "expires_at",
            "exam_date",
            "sort_order",
            "is_active",
            "dob_start_date",
            "dob_end_date",
            "eligible_qualifications",
        ]
        labels = {
            "title": "Exam title",
            "description": "Short description",
            "status": "Publication status",
            "publish_at": "Show from (optional)",
            "expires_at": "Hide after (optional)",
            "exam_date": "Exam date (optional)",
            "sort_order": "Display order",
            "is_active": "Active",
            "dob_start_date": "DOB starting date",
            "dob_end_date": "DOB ending date",
            "eligible_qualifications": "Eligible qualifications",
        }
        help_texts = {
            "title": "Shown as the heading of the exam card.",
            "description": "Optional supporting text shown under the exam title.",
            "status": "Only published exams appear on the public website.",
            "publish_at": "Leave empty to show the exam immediately.",
            "expires_at": "Leave empty to keep the exam visible until you unpublish it.",
            "exam_date": (
                "Date the exam is held. Exams with a date of today or later appear in "
                "Upcoming Exams; exams with a past date appear in Recent Exams. "
                "Leave empty to show the exam only in the general Exams section."
            ),
            "sort_order": "Lower numbers appear first.",
            "is_active": "Inactive exams are hidden from the public website even when published.",
            "dob_start_date": "Earliest eligible candidate date of birth (inclusive). This is a candidate DOB boundary, not the application opening date.",
            "dob_end_date": "Latest eligible candidate date of birth (inclusive). This is a candidate DOB boundary, not the application closing date.",
            "eligible_qualifications": "Tick every qualification accepted for this exam. A candidate qualifies if their qualification matches any ticked option.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "exam_date": forms.DateInput(attrs={"type": "date"}),
            "dob_start_date": forms.DateInput(attrs={"type": "date"}),
            "dob_end_date": forms.DateInput(attrs={"type": "date"}),
            "eligible_qualifications": forms.CheckboxSelectMultiple(
                attrs={"class": "management-checkbox-grid"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.required = (name == "title")
        for name, field in self.fields.items():
            detail = field.help_text or f"Controls this exam's {name.replace('_', ' ')}."
            field.help_text = PUBLIC_EXAM_LOCATION + detail
        self.fields["title"].widget.attrs.setdefault(
            "placeholder", "e.g. UPSC Civil Services 2026"
        )

    def clean(self):
        cleaned = super().clean()
        publish_at = cleaned.get("publish_at")
        expires_at = cleaned.get("expires_at")
        if publish_at and expires_at and expires_at <= publish_at:
            self.add_error(
                "expires_at", "Hide-after date must be later than the show-from date."
            )
        dob_start = cleaned.get("dob_start_date")
        dob_end = cleaned.get("dob_end_date")
        if dob_start and dob_end and dob_start > dob_end:
            self.add_error(
                "dob_start_date",
                "DOB starting date cannot be later than the DOB ending date.",
            )
        return cleaned


class ExamPDFForm(ManagementForm):
    """Attach a downloadable PDF (and optional external link) to an exam."""

    class Meta:
        model = ExamPDF
        fields = [
            "display_name",
            "pdf_file",
            "external_link",
            "link_text",
            "sort_order",
            "is_active",
        ]
        labels = {
            "display_name": "PDF name",
            "pdf_file": "PDF file",
            "external_link": "External link (optional)",
            "link_text": "External link text (optional)",
            "sort_order": "Display order",
            "is_active": "Active",
        }
        help_texts = {
            "display_name": "Text shown on the public download link, e.g. “Official Notification”.",
            "pdf_file": "PDF only, maximum 20 MB.",
            "external_link": "Optional link to an official page, e.g. the online application form.",
            "link_text": "Text shown for the external link. Defaults to the link itself.",
            "sort_order": "Lower numbers appear first.",
            "is_active": "Inactive PDFs are hidden from the public website.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["pdf_file"].required = False
        for name, field in self.fields.items():
            detail = field.help_text or f"Controls this PDF's {name.replace('_', ' ')}."
            field.help_text = PUBLIC_EXAM_LOCATION + detail
        self.fields["pdf_file"].widget.attrs["accept"] = ".pdf,application/pdf"
        self.fields["pdf_file"].widget.attrs["data-test-link"] = "true"

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk and not cleaned.get("pdf_file"):
            self.add_error("pdf_file", "Upload the PDF file for this exam.")
        return cleaned


class ExamResourceForm(ManagementForm):
    """Shared setup for the exam-linked resource forms.

    Every resource stores a title, a link to an exam, a description, a
    publication status, a publication date, a display order, and an optional or
    required PDF. The concrete subclasses only declare their own extra fields.
    """

    location_prefix = ""
    pdf_label = "PDF file"
    pdf_required = False
    pdf_required_message = "Upload the PDF file."
    required_pdf_help = (
        "PDF only, maximum size is configured with CMS_MAX_PDF_SIZE (default 20 MB)."
    )
    optional_pdf_help = (
        "Optional PDF. PDF only, maximum size is configured with CMS_MAX_PDF_SIZE (default 20 MB)."
    )
    groups = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.required = (name == "title")
        if "exam" in self.fields:
            self.fields["exam"].queryset = Exam.objects.order_by(
                "sort_order", "title"
            )
            self.fields["exam"].required = False
        for date_field in ("published_date", "closing_date"):
            if date_field in self.fields:
                self.fields[date_field].widget = forms.DateInput(attrs={"type": "date"})
        if "pdf_file" in self.fields:
            self.fields["pdf_file"].required = False
            self.fields["pdf_file"].label = self.pdf_label
            self.fields["pdf_file"].help_text = self.optional_pdf_help
            self.fields["pdf_file"].widget.attrs["accept"] = ".pdf,application/pdf"
            self.fields["pdf_file"].widget.attrs["data-test-link"] = "true"
        for name, field in self.fields.items():
            if name in {"pdf_file"}:
                continue
            detail = field.help_text or f"Controls this item's {name.replace('_', ' ')}."
            field.help_text = self.location_prefix + detail
        self.field_groups = [
            (title, [self[name] for name in names if name in self.fields])
            for title, names in self.groups
            if any(name in self.fields for name in names)
        ]

    def clean(self):
        cleaned = super().clean()
        if self.pdf_required and not self.instance.pk and not cleaned.get("pdf_file"):
            self.add_error("pdf_file", self.pdf_required_message)
        self._require_pdf_or_url(cleaned)
        return cleaned

    def _require_pdf_or_url(self, cleaned):
        """Subclasses override to enforce "PDF or URL" resources."""


ANSWER_SHEET_PUBLIC_LOCATION = "Public location: the Answer Sheet page. "
REGISTRATION_PUBLIC_LOCATION = "Public location: the Registration Form page. "
PREVIOUS_PAPER_PUBLIC_LOCATION = "Public location: the Previous Paper page. "
RESULT_PUBLIC_LOCATION = "Public location: the Result page. "
LATEST_JOB_PUBLIC_LOCATION = "Public location: the Latest Jobs page and the homepage. "


class ResourceURLForm(ManagementForm):
    """Form for managing a single ResourceURL instance."""

    class Meta:
        model = ResourceURL
        fields = ["label", "url", "target", "sort_order", "is_active"]
        labels = {
            "label": "Link label",
            "url": "Destination URL",
            "target": "Open in",
            "sort_order": "Display order",
            "is_active": "Active",
        }
        help_texts = {
            "label": "Visible text for the link, e.g., 'Download Notification' or 'Apply Online'.",
            "url": "HTTP/HTTPS URL or internal path starting with /.",
            "target": "Whether the link opens in the same tab or a new tab.",
            "sort_order": "Lower numbers appear first.",
            "is_active": "Inactive links are hidden from the public website.",
        }


class AnswerSheetForm(ExamResourceForm):
    """Create or edit a downloadable answer-sheet PDF."""

    location_prefix = ANSWER_SHEET_PUBLIC_LOCATION
    pdf_required = False
    pdf_required_message = "Upload the answer-sheet PDF."
    groups = (
        (
            "Answer sheet",
            ("title", "exam", "description", "pdf_file"),
        ),
        (
            "Publishing",
            ("status", "published_date", "sort_order", "is_active"),
        ),
    )

    class Meta:
        model = AnswerSheet
        fields = [
            "title",
            "exam",
            "description",
            "pdf_file",
            "status",
            "published_date",
            "sort_order",
            "is_active",
        ]
        labels = {
            "title": "Answer-sheet title",
            "exam": "Related exam (optional)",
            "description": "Description or instructions",
            "pdf_file": "Answer-sheet PDF",
            "status": "Publication status",
            "published_date": "Publication date (optional)",
            "sort_order": "Display order",
            "is_active": "Active",
        }
        help_texts = {
            "title": "Shown as the heading of the public listing entry.",
            "exam": "Optional exam this answer sheet belongs to.",
            "description": "Optional instructions shown with the public link.",
            "status": "Only published items appear on the public website.",
            "published_date": "Leave empty to publish immediately, or set a future date to hide the item until then.",
            "sort_order": "Lower numbers appear first.",
            "is_active": "Inactive items are hidden from the public website.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class RegistrationResourceForm(ExamResourceForm):
    """Create or edit a registration/application resource (PDF and/or URL)."""

    location_prefix = REGISTRATION_PUBLIC_LOCATION
    pdf_required = False
    groups = (
        (
            "Registration resource",
            ("title", "exam", "description", "pdf_file", "official_url", "closing_date"),
        ),
        (
            "Publishing",
            ("status", "published_date", "sort_order", "is_active"),
        ),
    )

    class Meta:
        model = RegistrationResource
        fields = [
            "title",
            "exam",
            "description",
            "pdf_file",
            "official_url",
            "closing_date",
            "status",
            "published_date",
            "sort_order",
            "is_active",
        ]
        labels = {
            "title": "Registration title",
            "exam": "Related exam (optional)",
            "description": "Description or instructions",
            "pdf_file": "Application PDF (optional)",
            "official_url": "Official application URL (optional)",
            "closing_date": "Last date to apply (optional)",
            "status": "Publication status",
            "published_date": "Publication date (optional)",
            "sort_order": "Display order",
            "is_active": "Active",
        }
        help_texts = {
            "title": "Shown as the heading of the public listing entry.",
            "exam": "Optional exam this registration resource belongs to.",
            "description": "Optional instructions shown with the public resource.",
            "official_url": "Official application page (http/https). Provide this, an application PDF, or both.",
            "closing_date": "Optional last date to apply shown on the public page.",
            "status": "Only published items appear on the public website.",
            "published_date": "Leave empty to publish immediately, or set a future date to hide the item until then.",
            "sort_order": "Lower numbers appear first.",
            "is_active": "Inactive items are hidden from the public website.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def _require_pdf_or_url(self, cleaned):
        pass


class PreviousPaperForm(ExamResourceForm):
    """Create or edit a previous-year question paper (PDF required)."""

    location_prefix = PREVIOUS_PAPER_PUBLIC_LOCATION
    pdf_required = False
    pdf_required_message = "Upload the paper PDF."
    groups = (
        (
            "Previous paper",
            ("title", "exam", "exam_year", "description", "pdf_file"),
        ),
        (
            "Publishing",
            ("status", "published_date", "sort_order", "is_active"),
        ),
    )

    class Meta:
        model = PreviousPaper
        fields = [
            "title",
            "exam",
            "exam_year",
            "description",
            "pdf_file",
            "status",
            "published_date",
            "sort_order",
            "is_active",
        ]
        labels = {
            "title": "Paper title",
            "exam": "Related exam (optional)",
            "exam_year": "Exam year",
            "description": "Description",
            "pdf_file": "Paper PDF",
            "status": "Publication status",
            "published_date": "Publication date (optional)",
            "sort_order": "Display order",
            "is_active": "Active",
        }
        help_texts = {
            "title": "Shown as the heading of the public listing entry.",
            "exam": "Optional exam this paper belongs to.",
            "exam_year": "Year the paper was held, e.g. 2025.",
            "description": "Optional description shown with the public download link.",
            "status": "Only published items appear on the public website.",
            "published_date": "Leave empty to publish immediately, or set a future date to hide the item until then.",
            "sort_order": "Lower numbers appear first.",
            "is_active": "Inactive items are hidden from the public website.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_exam_year(self):
        year = self.cleaned_data.get("exam_year")
        if year is None:
            return year
        current_year = timezone.localdate().year
        if year < 1900 or year > current_year + 2:
            raise forms.ValidationError(
                f"Enter an exam year between 1900 and {current_year + 2}."
            )
        return year


class ResultForm(ExamResourceForm):
    """Create or edit a result announcement (official URL and/or PDF)."""

    location_prefix = RESULT_PUBLIC_LOCATION
    pdf_required = False
    groups = (
        (
            "Result announcement",
            ("title", "exam", "description", "official_url", "pdf_file"),
        ),
        (
            "Publishing",
            ("status", "published_date", "sort_order", "is_active"),
        ),
    )

    class Meta:
        model = Result
        fields = [
            "title",
            "exam",
            "description",
            "official_url",
            "pdf_file",
            "status",
            "published_date",
            "sort_order",
            "is_active",
        ]
        labels = {
            "title": "Result title",
            "exam": "Related exam (optional)",
            "description": "Result description or announcement details",
            "official_url": "Official result URL (optional)",
            "pdf_file": "Result PDF (optional)",
            "status": "Publication status",
            "published_date": "Result publication date (optional)",
            "sort_order": "Display order",
            "is_active": "Active",
        }
        help_texts = {
            "title": "Shown as the heading of the public result entry.",
            "exam": "Optional exam this result belongs to.",
            "description": "Optional announcement details shown with the public entry.",
            "official_url": "Official result page (http/https). Provide this, a result PDF, or both.",
            "status": "Only published results appear on the public website.",
            "published_date": "Leave empty to publish immediately, or set a future date to hide the result until then.",
            "sort_order": "Lower numbers appear first.",
            "is_active": "Inactive results are hidden from the public website.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def _require_pdf_or_url(self, cleaned):
        pass


class LatestJobForm(ExamResourceForm):
    """Create or edit a latest job posting (photo, official URL and/or PDF)."""

    location_prefix = LATEST_JOB_PUBLIC_LOCATION
    pdf_label = "Notification PDF (optional)"
    groups = (
        (
            "Job posting",
            ("title", "exam", "description", "image", "official_url", "pdf_file"),
        ),
        (
            "Publishing",
            ("status", "published_date", "sort_order", "is_active"),
        ),
    )

    class Meta:
        model = LatestJob
        fields = [
            "title",
            "exam",
            "description",
            "image",
            "official_url",
            "pdf_file",
            "status",
            "published_date",
            "sort_order",
            "is_active",
        ]
        labels = {
            "title": "Job title",
            "exam": "Related exam (optional)",
            "description": "Description or job details",
            "image": "Photo (optional)",
            "official_url": "Official job URL (optional)",
            "status": "Publication status",
            "published_date": "Publication date (optional)",
            "sort_order": "Display order",
            "is_active": "Active",
        }
        help_texts = {
            "title": "Shown as the heading of the public job card and detail page.",
            "exam": "Optional exam or recruitment this job posting belongs to.",
            "description": "Short summary shown on the job card and detail page.",
            "official_url": "Official notification or application page (http/https). Provide this, a notification PDF, or both.",
            "status": "Only published jobs appear on the public website.",
            "published_date": "Leave empty to publish immediately, or set a future date to hide the job until then.",
            "sort_order": "Lower numbers appear first. Jobs also appear first on the homepage.",
            "is_active": "Inactive jobs are hidden from the public website.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "image" in self.fields:
            self.fields["image"].widget.attrs["accept"] = "image/png,image/jpeg,image/webp"
            self.fields["image"].widget.attrs["data-test-link"] = "true"

    def _require_pdf_or_url(self, cleaned):
        pass

