"""Curated inline-SVG icon registry for the Sarkari Result CMS.

Every entry stores a validated identifier; templates render the matching
inline SVG from ``accounts/includes/portal_icon.html``. Arbitrary text is
never treated as an icon — unknown values fall back to a neutral default.
"""

ICON_CHOICES = [
    ("phone", "Phone"),
    ("email", "Email"),
    ("location", "Location"),
    ("home", "Home"),
    ("search", "Search"),
    ("user", "User"),
    ("calendar", "Calendar"),
    ("document", "Document"),
    ("briefcase", "Job"),
    ("result", "Result"),
    ("book", "Admission"),
    ("ticket", "Admit Card"),
    ("key", "Answer Key"),
    ("paper", "Notification"),
    ("notice", "Notice"),
    ("link", "Link"),
    ("facebook", "Facebook"),
    ("instagram", "Instagram"),
    ("whatsapp", "WhatsApp"),
    ("contact", "Contact"),
    ("info", "Information"),
    ("tools", "Tools"),
    ("image", "Image"),
    ("badge-check", "Verified badge"),
]

KNOWN_ICONS = frozenset(slug for slug, _label in ICON_CHOICES)

DEFAULT_ICON = "info"
