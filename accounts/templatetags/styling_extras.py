"""Template helpers that render the shared, whitelisted text styling.

Both tags delegate to :mod:`site_management.styling`, so no template ever
hard-codes a styling rule and every block type reuses the same helper. Each
returned declaration comes from a fixed whitelist of properties and values, so
a stored (or tampered) value can never inject markup or arbitrary CSS.
"""

from django import template

from site_management import styling

register = template.Library()


@register.simple_tag
def element_style(obj, element):
    """Return the safe CSS string for one text element of a block."""
    if obj is None:
        return ""
    return styling.resolve_element_style(obj, element)


@register.simple_tag
def style_order_class(obj):
    """Return the flex-order opt-in class only when the block set an order.

    Applying the class per block means one block's ordering can never re-order
    another block's text.
    """
    if obj is None or not styling.uses_order(obj):
        return ""
    return "portal-styled-order"
