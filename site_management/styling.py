"""Reusable, global text-styling engine.

Every supported content block (homepage cards, Results, Admit Cards, Previous
Year Papers, Answer Keys, Syllabus, Updates, Exams, Tools, Website pages and
the header/footer text) stores its per-element presentation in a single
``text_styles`` JSON dictionary. This module is the one shared place that:

* declares the supported text elements (the *registry*),
* declares the allowed values for each control,
* validates and sanitises whatever an administrator submits, and
* turns a stored entry into a short, safe, whitelisted CSS string.

Because the registry and the renderer live here — and not inside any single
block's form or template — a *future* content block can reuse the exact same
editor by adding one line to ``ELEMENT_SETS``. Nothing in this module writes
HTML: it only ever emits a handful of properties from fixed whitelists, so a
stored value can never inject markup.
"""

from __future__ import annotations

import re

HEX_COLOR_RE = re.compile(r"\A#[0-9A-Fa-f]{6}\Z")


# ---------------------------------------------------------------------------
# 1. The element registry — semantic text slots shared by every block.
# ---------------------------------------------------------------------------
TEXT_ELEMENTS = {
    "title": "Title / heading",
    "subtitle": "Subtitle",
    "eyebrow": "Eyebrow / small label",
    "badge": "Badge text",
    "highlight": "Highlight line",
    "description": "Description",
    "body": "Paragraph / body text",
    "caption": "Caption",
    "source": "Source line",
    "link_label": "Link title",
    "link_url": "URL / link text",
    "button": "Button label",
    "cta": "Call to action",
    "section_title": "Section heading",
    "section_description": "Section description",
    "announcement": "Announcement",
    "tool_title": "Tool title",
    "tool_description": "Tool description",
    "header_text": "Header text",
    "brand_name": "Website name",
    "tagline": "Tagline",
    "footer_text": "Footer text",
    "footer_link": "Footer link",
}

# Which elements are relevant for each kind of editor. Unknown/new blocks fall
# back to ``DEFAULT_ELEMENTS`` so the same editor keeps working everywhere.
DEFAULT_ELEMENTS = (
    "title",
    "subtitle",
    "description",
    "body",
    "link_label",
    "link_url",
    "button",
    "cta",
)

ELEMENT_SETS = {
    "content_item": (
        "title",
        "subtitle",
        "eyebrow",
        "badge",
        "highlight",
        "description",
        "body",
        "caption",
        "source",
        "link_label",
        "link_url",
        "button",
        "cta",
    ),
    "exam": ("title", "description", "link_label", "link_url"),
    "exam_pdf": ("link_label",),
    "content_link": ("link_label", "link_url", "description"),
    # A dynamic "Add URL" entry only ever shows its visible text: the label.
    # Its destination is an href, never rendered text, so there is no URL
    # styling group — for Icon, Link and Text entries alike.
    "nested_link": ("link_label",),
    "tool": ("tool_title", "tool_description"),
    "website_page": ("title", "subtitle", "description"),
    "section": ("section_title", "section_description"),
    "announcement": ("announcement", "link_label", "link_url"),
    "header": ("brand_name", "tagline", "header_text"),
    "footer": ("footer_text", "footer_link"),
    "settings": (
        "brand_name",
        "tagline",
        "header_text",
        "title",
        "subtitle",
        "description",
        "announcement",
        "footer_text",
    ),
}

#: The form field that backs each semantic element, per editor context. A
#: styling group is only offered when its backing field is actually present on
#: the form being edited, so a simplified form (for example the Title /
#: Description-only exam editor) never shows controls for text fields it does
#: not have. ``None`` marks an element that has no backing field in that
#: context and must therefore never be offered.
ELEMENT_FORM_FIELDS = {
    "content_item": {
        "title": "label",
        "subtitle": "subtitle",
        "eyebrow": "eyebrow_text",
        "badge": "badge_text",
        "highlight": "highlight_text",
        "description": "short_description",
        "body": "body",
        "caption": "caption",
        "source": "source_name",
        "link_label": "link_title",
        "link_url": None,
        "button": "button_text",
        "cta": "call_to_action",
    },
    "exam": {
        "title": "title",
        "description": "description",
        "link_label": None,
        "link_url": None,
    },
    "exam_pdf": {"link_label": "display_name"},
    "content_link": {
        "link_label": "label",
        "link_url": "url",
        "description": "description",
    },
    "nested_link": {"link_label": "label"},
    "tool": {"tool_title": "label", "tool_description": "body"},
    "website_page": {"title": "title", "subtitle": "subtitle", "description": "body"},
    "section": {"section_title": "title", "section_description": "description"},
    "announcement": {"announcement": "label", "link_label": None, "link_url": None},
    "header": {
        "brand_name": "site_name",
        "tagline": "tagline",
        "header_text": "header_text",
    },
    "footer": {"footer_text": "footer_description", "footer_link": None},
    "settings": {
        "brand_name": "site_name",
        "tagline": "tagline",
        "header_text": "header_text",
        "title": "hero_title",
        "subtitle": None,
        "description": "hero_description",
        "announcement": "announcement",
        "footer_text": "footer_description",
    },
}


def element_form_field(context, element):
    """Return the form field that backs ``element`` in ``context``.

    Returns ``None`` when the element has no backing field and must therefore
    not be offered. Contexts without an explicit map (a block added later) fall
    back to matching a form field with the same name as the element, so the
    editor keeps working for new blocks without editing this table.
    """
    mapping = ELEMENT_FORM_FIELDS.get(context)
    if mapping is None:
        return element
    return mapping.get(element)


def elements_for(context, field_names=None):
    """Return the ordered ``(key, label)`` pairs relevant to an editor context.

    When ``field_names`` is given (the names of the fields the form actually
    has), elements whose backing field is absent — or whose element has no
    backing field at all — are left out, so a form only ever shows styling
    controls for the text fields it genuinely contains.
    """
    keys = ELEMENT_SETS.get(context, DEFAULT_ELEMENTS)
    pairs = [(key, TEXT_ELEMENTS[key]) for key in keys if key in TEXT_ELEMENTS]
    if field_names is None:
        return pairs
    available = set(field_names)
    return [
        (key, label)
        for key, label in pairs
        if element_form_field(context, key) in available
    ]


# ---------------------------------------------------------------------------
# 2. Allowed values for every control.
# ---------------------------------------------------------------------------
FONT_SIZE_CHOICES = [
    ("", "Default"),
    ("xs", "Extra small"),
    ("sm", "Small"),
    ("md", "Normal"),
    ("lg", "Large"),
    ("xl", "Extra large"),
    ("2xl", "2x large"),
    ("3xl", "3x large"),
]
FONT_SIZE_VALUES = {
    "xs": "0.8rem",
    "sm": "0.9rem",
    "md": "1rem",
    "lg": "1.15rem",
    "xl": "1.35rem",
    "2xl": "1.6rem",
    "3xl": "1.95rem",
}

FONT_WEIGHT_CHOICES = [
    ("", "Default"),
    ("light", "Light"),
    ("normal", "Normal"),
    ("medium", "Medium"),
    ("semibold", "Semibold"),
    ("bold", "Bold"),
]
FONT_WEIGHT_VALUES = {
    "light": "300",
    "normal": "400",
    "medium": "500",
    "semibold": "600",
    "bold": "700",
}

FONT_STYLE_CHOICES = [
    ("", "Default"),
    ("normal", "Normal"),
    ("italic", "Italic"),
]
FONT_STYLE_VALUES = {"normal": "normal", "italic": "italic"}

# The editor offers exactly Left / Centre / Right (plus Default). "justify"
# stays in ALIGN_VALUES so any value saved by an older editor still renders.
ALIGN_CHOICES = [
    ("", "Default"),
    ("left", "Left"),
    ("center", "Centre"),
    ("right", "Right"),
]
ALIGN_VALUES = {
    "left": "left",
    "center": "center",
    "right": "right",
    "justify": "justify",
}

SPACING_CHOICES = [
    ("", "Default"),
    ("none", "None"),
    ("compact", "Compact"),
    ("normal", "Normal"),
    ("relaxed", "Relaxed"),
]
# key -> (margin-top, margin-bottom, line-height)
SPACING_VALUES = {
    "none": ("0", "0", "1.3"),
    "compact": ("0.15rem", "0.35rem", "1.4"),
    "normal": ("0.4rem", "0.6rem", "1.55"),
    "relaxed": ("0.8rem", "1.05rem", "1.7"),
}

MARGIN_CHOICES = [
    ("", "Default"),
    ("none", "None"),
    ("xs", "Extra small"),
    ("sm", "Small"),
    ("md", "Medium"),
    ("lg", "Large"),
    ("xl", "Extra large"),
]
MARGIN_VALUES = {
    "none": "0",
    "xs": "0.15rem",
    "sm": "0.35rem",
    "md": "0.6rem",
    "lg": "1rem",
    "xl": "1.5rem",
}

ORDER_MIN = 0
ORDER_MAX = 20

# The properties an entry may contain, in rendering order.
STYLE_PROPERTIES = (
    "color",
    "size",
    "weight",
    "style",
    "align",
    "spacing",
    "order",
    "margin_top",
    "margin_bottom",
)


# ---------------------------------------------------------------------------
# 3. Sanitising submitted values.
# ---------------------------------------------------------------------------
def _clean_color(value):
    value = (value or "").strip()
    return value if HEX_COLOR_RE.match(value) else ""


def _clean_choice(value, allowed):
    value = (value or "").strip()
    return value if value in allowed else ""


def _clean_order(value):
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return ""
    return str(number) if ORDER_MIN <= number <= ORDER_MAX else ""


def sanitize_text_styles(raw):
    """Return a validated, whitelisted copy of a submitted styling dictionary.

    Unknown element keys and unknown/invalid control values are silently
    dropped, so a tampered POST cannot smuggle arbitrary CSS or markup into the
    public pages.
    """
    if not isinstance(raw, dict):
        return {}

    clean = {}
    for element, entry in raw.items():
        if element not in TEXT_ELEMENTS or not isinstance(entry, dict):
            continue
        cleaned = {}
        color = _clean_color(entry.get("color"))
        if color:
            cleaned["color"] = color
        size = _clean_choice(entry.get("size"), FONT_SIZE_VALUES)
        if size:
            cleaned["size"] = size
        weight = _clean_choice(entry.get("weight"), FONT_WEIGHT_VALUES)
        if weight:
            cleaned["weight"] = weight
        font_style = _clean_choice(entry.get("style"), FONT_STYLE_VALUES)
        if font_style:
            cleaned["style"] = font_style
        align = _clean_choice(entry.get("align"), ALIGN_VALUES)
        if align:
            cleaned["align"] = align
        spacing = _clean_choice(entry.get("spacing"), SPACING_VALUES)
        if spacing:
            cleaned["spacing"] = spacing
        order = _clean_order(entry.get("order"))
        if order:
            cleaned["order"] = order
        margin_top = _clean_choice(entry.get("margin_top"), MARGIN_VALUES)
        if margin_top:
            cleaned["margin_top"] = margin_top
        margin_bottom = _clean_choice(entry.get("margin_bottom"), MARGIN_VALUES)
        if margin_bottom:
            cleaned["margin_bottom"] = margin_bottom
        if cleaned:
            clean[element] = cleaned
    return clean


# ---------------------------------------------------------------------------
# 4. Rendering a stored entry to safe CSS.
# ---------------------------------------------------------------------------
def build_style(entry):
    """Turn one validated entry into a safe CSS declaration string."""
    if not isinstance(entry, dict):
        return ""
    declarations = []

    color = _clean_color(entry.get("color"))
    if color:
        declarations.append(f"color:{color}")

    size = FONT_SIZE_VALUES.get(entry.get("size"))
    if size:
        declarations.append(f"font-size:{size}")

    weight = FONT_WEIGHT_VALUES.get(entry.get("weight"))
    if weight:
        declarations.append(f"font-weight:{weight}")

    font_style = FONT_STYLE_VALUES.get(entry.get("style"))
    if font_style:
        declarations.append(f"font-style:{font_style}")

    align = ALIGN_VALUES.get(entry.get("align"))
    if align:
        declarations.append(f"text-align:{align}")

    spacing = SPACING_VALUES.get(entry.get("spacing"))
    if spacing:
        margin_top, margin_bottom, line_height = spacing
        declarations.append(f"margin-top:{margin_top}")
        declarations.append(f"margin-bottom:{margin_bottom}")
        declarations.append(f"line-height:{line_height}")

    margin_top = MARGIN_VALUES.get(entry.get("margin_top"))
    if margin_top is not None:
        declarations.append(f"margin-top:{margin_top}")

    margin_bottom = MARGIN_VALUES.get(entry.get("margin_bottom"))
    if margin_bottom is not None:
        declarations.append(f"margin-bottom:{margin_bottom}")

    order = _clean_order(entry.get("order"))
    if order:
        declarations.append(f"order:{order}")

    return ";".join(declarations)


def get_store(obj):
    """Return the styling dictionary stored on a model instance or dict row."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        store = obj.get("text_styles")
    else:
        store = getattr(obj, "text_styles", None)
    return store if isinstance(store, dict) else {}


def _stored_value(obj, key):
    """Read a value from a model instance or from a view-built dict row."""
    if isinstance(obj, dict):
        return obj.get(key) or ""
    return getattr(obj, key, "") or ""


def _legacy_background(obj, prefix):
    """Reproduce the legacy title/subtitle background treatment, if set."""
    value = _stored_value(obj, f"{prefix}_background_color")
    if value and HEX_COLOR_RE.match(value):
        return (
            f"background-color:{value};display:inline-block;padding:.12em .32em"
        )
    return ""


def resolve_element_style(obj, element):
    """Return the full, safe CSS string for one element of one block.

    The per-element ``text_styles`` entry is merged over the legacy
    ``title_color``/``subtitle_color`` columns so existing saved colours keep
    working exactly as before. Model instances and the lightweight dicts built
    by the public views are both supported.
    """
    entry = dict(get_store(obj).get(element) or {})

    if element in {"title", "subtitle"} and not entry.get("color"):
        legacy = _stored_value(obj, f"{element}_color")
        if legacy and HEX_COLOR_RE.match(legacy):
            entry["color"] = legacy

    css = build_style(entry)

    if element in {"title", "subtitle"}:
        legacy_background = _legacy_background(obj, element)
        if legacy_background:
            css = f"{css};{legacy_background}" if css else legacy_background

    return css


def uses_order(obj):
    """True when any element of this block sets a custom display order.

    Templates use this to opt the block's text container into a flex column so
    the per-element ``order`` values can take effect — one block's ordering can
    therefore never re-order another block's text.
    """
    store = get_store(obj)
    return any(
        isinstance(entry, dict) and entry.get("order")
        for entry in store.values()
    )
