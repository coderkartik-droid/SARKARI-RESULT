from urllib.parse import urlsplit

from django import template

register = template.Library()


@register.filter
def normalize_href(value):
    if not value:
        return ''
    if value.startswith('#'):
        return value
    if value.startswith('/'):
        return value
    return value.strip()


@register.filter
def is_external_url(value):
    if not value:
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return bool(parsed.scheme in {'http', 'https'})


@register.filter
def url_label(value):
    return value.strip() if isinstance(value, str) else value

