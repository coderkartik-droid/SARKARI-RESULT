from django import template

from site_management.navigation import build_navigation, sidebar_stats


register = template.Library()


@register.filter
def get_item(mapping, key):
    if not isinstance(mapping, dict):
        return None
    return mapping.get(key)


@register.simple_tag
def get_sidebar_stats():
    """Return lightweight counts for sidebar badges (unread messages, pending comments)."""
    return sidebar_stats()


@register.simple_tag(takes_context=True)
def management_nav(context):
    """Resolve the six-section workspace sidebar for the current request user."""
    request = context.get("request")
    if request is None:
        return []
    return build_navigation(
        request.user,
        current_path=request.path,
        stats=sidebar_stats(),
    )
