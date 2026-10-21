"""The one reusable visual text editor shared by every content block.

Any management form that edits a public text block mixes in
``TextStyleEditorMixin`` and states which registry context it belongs to
(``style_context = "exam"``, ``"content_item"``, …). The mixin then adds one
small control per supported text element from :mod:`site_management.styling`
and writes the validated result into the block's ``text_styles`` dictionary.

Nothing here is Exams-specific and nothing is hand-written per section: adding
a brand-new block later means adding one entry to
``styling.ELEMENT_SETS`` and giving its form the same mixin — the editor, its
validation and its public rendering all follow automatically.
"""

import copy

from django import forms

from . import styling
from .models import HEX_COLOR_VALIDATOR

#: Exactly the controls the content editor offers for every text element
#: (Title, Description, …): margin top/bottom, colour, size, weight,
#: normal/italic and alignment. Every control has a "Default" option, which
#: means "keep the website's existing styling".
STYLE_CONTROLS = (
    {
        "prop": "margin_top",
        "label": "Margin top",
        "kind": "select",
        "choices": styling.MARGIN_CHOICES,
    },
    {
        "prop": "margin_bottom",
        "label": "Margin bottom",
        "kind": "select",
        "choices": styling.MARGIN_CHOICES,
    },
    {"prop": "color", "label": "Text colour", "kind": "color"},
    {
        "prop": "size",
        "label": "Font size",
        "kind": "select",
        "choices": styling.FONT_SIZE_CHOICES,
    },
    {
        "prop": "weight",
        "label": "Font weight",
        "kind": "select",
        "choices": styling.FONT_WEIGHT_CHOICES,
    },
    {
        "prop": "style",
        "label": "Font style",
        "kind": "select",
        "choices": styling.FONT_STYLE_CHOICES,
    },
    {
        "prop": "align",
        "label": "Text alignment",
        "kind": "select",
        "choices": styling.ALIGN_CHOICES,
    },
)


class TextStyleEditorMixin:
    """Add per-element styling controls to a management form.

    Subclasses set :attr:`style_context` to one of the keys understood by
    ``styling.elements_for`` and call :meth:`init_text_styles` at the end of
    their ``__init__``. Bound values are collected in :meth:`clean` and stored
    on the instance only after ``styling.sanitize_text_styles`` has validated
    them, so an edited or tampered POST can never inject arbitrary CSS.
    """

    #: Registry context, e.g. ``"content_item"``, ``"exam"``, ``"footer"``.
    style_context = None
    #: Field-name namespace so the controls cannot clash with editor fields.
    style_field_prefix = "style"

    def init_text_styles(self, context=None):
        context = context or self.style_context
        store = styling.get_store(getattr(self, "instance", None))
        # Only offer a styling group when the form really contains the text
        # field it styles, so a simplified form never shows controls for fields
        # it does not have (and never submits them).
        field_names = {name for name in self.fields if not name.startswith(self.style_field_prefix + "_")}
        self._style_field_map = {}
        self.style_groups = []
        for element, element_label in styling.elements_for(context, field_names):
            entry = store.get(element) or {}
            if not isinstance(entry, dict):
                entry = {}
            fields = []
            for control in STYLE_CONTROLS:
                prop = control["prop"]
                name = f"{self.style_field_prefix}_{element}_{prop}"
                field = self._build_style_field(
                    control, entry.get(prop, ""), element_label
                )
                self.fields[name] = field
                self._style_field_map[name] = (element, prop)
                # Store the *bound* field, not the raw field object: templates
                # render `{{ field }}` to draw the widget, and a bare Field would
                # print its repr (e.g. "<django.forms.fields.CharField object at ...>").
                fields.append(self[name])
            self.style_groups.append(
                {"key": element, "label": element_label, "fields": fields}
            )

    def _build_style_field(self, control, current, element_label):
        prop = control["prop"]
        attrs = {
            "class": "management-input management-style-input",
            "aria-label": f"{element_label}: {control['label']}",
        }
        if control["kind"] == "color":
            attrs.update({"placeholder": "#RRGGBB", "spellcheck": "false"})
            return forms.CharField(
                required=False,
                label=control["label"],
                initial=current or "",
                validators=[HEX_COLOR_VALIDATOR],
                widget=forms.TextInput(attrs=attrs),
            )
        if control["kind"] == "order":
            try:
                initial = int(current)
            except (TypeError, ValueError):
                initial = None
            attrs.update(
                {
                    "min": styling.ORDER_MIN,
                    "max": styling.ORDER_MAX,
                    "inputmode": "numeric",
                }
            )
            return forms.IntegerField(
                required=False,
                label=control["label"],
                initial=initial,
                min_value=styling.ORDER_MIN,
                max_value=styling.ORDER_MAX,
                widget=forms.NumberInput(attrs=attrs),
            )
        choices = list(control["choices"])
        # Preserve a value saved by an older editor that no longer offers it
        # (for example "justify" on alignment) so opening and saving a record
        # can never silently discard it.
        if current and current not in {value for value, _label in choices}:
            choices.append((current, f"{current.title()} (saved)"))
        return forms.ChoiceField(
            required=False,
            label=control["label"],
            initial=current or "",
            choices=choices,
            widget=forms.Select(attrs=attrs),
        )

    def collect_text_styles(self, cleaned_data):
        """Return the sanitised ``text_styles`` dictionary for this submit.

        The saved store is the starting point, so an element whose styling
        controls were not part of this form (or whose group is hidden for the
        selected URL-entry type) keeps its saved values. Only elements whose
        controls were actually submitted are rebuilt — from the submitted
        values, or removed when every control is back on "Default".
        """
        existing = styling.get_store(getattr(self, "instance", None))
        store = copy.deepcopy(existing) if isinstance(existing, dict) else {}

        controls_by_element = {}
        for name, (element, prop) in getattr(self, "_style_field_map", {}).items():
            controls_by_element.setdefault(element, []).append((name, prop))

        submitted = getattr(self, "data", None)
        for element, controls in controls_by_element.items():
            if submitted is not None and not any(
                name in submitted for name, _prop in controls
            ):
                # Not rendered / not submitted: keep the previously saved
                # styling instead of silently discarding it.
                continue
            entry = {}
            for name, prop in controls:
                value = cleaned_data.get(name)
                if value in (None, ""):
                    continue
                entry[prop] = str(value)
            if entry:
                store[element] = entry
            else:
                store.pop(element, None)

        return styling.sanitize_text_styles(store)

    @property
    def style_has_errors(self):
        mapping = getattr(self, "_style_field_map", None)
        if not mapping or not self.is_bound:
            return False
        return any(self[name].errors for name in mapping)

    def style_summary(self):
        """Short human-readable summary of the elements with styling saved."""
        store = styling.get_store(getattr(self, "instance", None))
        return ", ".join(
            group["label"]
            for group in getattr(self, "style_groups", [])
            if group["key"] in store
        )

    def clean(self):
        cleaned = super().clean()
        if getattr(self, "_style_field_map", None) and hasattr(self, "instance"):
            self.instance.text_styles = self.collect_text_styles(cleaned)
        return cleaned
