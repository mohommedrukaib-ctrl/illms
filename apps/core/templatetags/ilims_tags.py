from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def active_nav(context, url_name, *args):
    """Return 'active' if current URL matches the given name pattern."""
    request = context.get("request")
    if not request:
        return ""
    current = request.resolver_match
    if not current:
        return ""
    # Match exact or namespace prefix
    names = [url_name] + list(args)
    for name in names:
        if current.url_name == name or (current.namespace and f"{current.namespace}:{current.url_name}" == name):
            return "active"
        # Match namespace prefix
        if current.namespace and current.namespace.startswith(name.split(":")[0]):
            if ":" not in name or current.url_name == name.split(":")[-1]:
                return "active"
    return ""


@register.filter(name="initials")
def initials_filter(user):
    """Return user initials."""
    if hasattr(user, "get_initials"):
        return user.get_initials()
    return "?"


@register.simple_tag
def icon(name, size="20", css_class=""):
    """
    Render an inline SVG icon. Using a minimal set of custom icons
    to avoid any external dependency.
    """
    icons = {
        "dashboard": '<path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z"/>',
        "sample": '<path d="M7 2v2H3.5C2.67 4 2 4.67 2 5.5v13C2 19.33 2.67 20 3.5 20h17c.83 0 1.5-.67 1.5-1.5v-13C22 4.67 21.33 4 20.5 4H17V2H7zm0 2h10v2H7V4z"/>',
        "flask": '<path d="M9 2v6.5L4 17v1c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-1l-5-8.5V2H9zm2 2h2v5.7l4.5 7.3H6.5L11 9.7V4z"/>',
        "report": '<path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zM6 20V4h7v5h5v11H6z"/>',
        "bell": '<path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/>',
        "settings": '<path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.63-.07.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>',
        "users": '<path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z"/>',
        "search": '<path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>',
        "logout": '<path d="M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z"/>',
        "lock": '<path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/>',
        "check": '<path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>',
        "close": '<path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>',
        "menu": '<path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/>',
        "sun": '<path d="M6.76 4.84l-1.8-1.79-1.41 1.41 1.79 1.79 1.42-1.41zM4 10.5H1v2h3v-2zm9-9.95h-2V3.5h2V.55zm7.45 3.91l-1.41-1.41-1.79 1.79 1.41 1.41 1.79-1.79zm-3.21 13.7l1.79 1.8 1.41-1.41-1.8-1.79-1.4 1.4zM20 10.5v2h3v-2h-3zm-8-5c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6-2.69-6-6-6zm-1 16.95h2V19.5h-2v2.95zm-7.45-3.91l1.41 1.41 1.79-1.8-1.41-1.41-1.79 1.8z"/>',
        "moon": '<path d="M10 2c-1.82 0-3.53.5-5 1.35C7.99 5.08 10 8.3 10 12s-2.01 6.92-5 8.65C6.47 21.5 8.18 22 10 22c5.52 0 10-4.48 10-10S15.52 2 10 2z"/>',
        "chevron-down": '<path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"/>',
        "chevron-right": '<path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/>',
        "plus": '<path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>',
        "print": '<path d="M19 8H5c-1.66 0-3 1.34-3 3v6h4v4h12v-4h4v-6c0-1.66-1.34-3-3-3zm-3 11H8v-5h8v5zm3-7c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-1-9H6v4h12V3z"/>',
        "fullscreen": '<path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/>',
        "client": '<path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>',
        "batch": '<path d="M20 2H4c-1 0-2 .9-2 2v3.01c0 .72.43 1.34 1 1.69V20c0 1.1 1.1 2 2 2h14c.9 0 2-.9 2-2V8.7c.57-.35 1-.97 1-1.69V4c0-1.1-1-2-2-2zm-5 12H9v-2h6v2zm5-7H4V4h16v3z"/>',
        "dna": '<path d="M4 2h2v2c0 .74.13 1.41.36 2H17.6c.26-.6.4-1.28.4-2V2h2v2c0 1.3-.4 2.5-1.1 3.5H5.1C4.4 6.5 4 5.3 4 4V2zm14.5 7.5c-.87.87-2.06 1.5-3.5 1.5h-6c-1.44 0-2.63-.63-3.5-1.5h13zM9 12h6c1.44 0 2.63.63 3.5 1.5h-13C6.37 12.63 7.56 12 9 12zm-3.64 4c-.23.59-.36 1.26-.36 2v2H3v-2c0-1.3.4-2.5 1.1-3.5h15.8c.7 1 1.1 2.2 1.1 3.5v2h-2v-2c0-.74-.13-1.41-.36-2H5.36z"/>',
        "qc": '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>',
        "reminder": '<path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2zm-2 1H8v-6c0-2.48 1.51-4.5 4-4.5s4 2.02 4 4.5v6z"/>',
        "audit": '<path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zM6 20V4h7v5h5v11H6zm3-7h6v2H9v-2zm0-3h6v2H9v-2z"/>',
        "microbe": '<circle cx="12" cy="12" r="6"/><line x1="12" y1="2" x2="12" y2="6" stroke="currentColor" stroke-width="2"/><line x1="12" y1="18" x2="12" y2="22" stroke="currentColor" stroke-width="2"/><line x1="2" y1="12" x2="6" y2="12" stroke="currentColor" stroke-width="2"/><line x1="18" y1="12" x2="22" y2="12" stroke="currentColor" stroke-width="2"/>',
    }

    svg_inner = icons.get(name, icons["check"])
    return mark_safe(
        f'<svg class="icon {css_class}" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
        f"{svg_inner}</svg>"
    )


@register.simple_tag
def theme_class(theme):
    """Return data-theme attribute value."""
    return theme if theme in ("light", "dark") else "light"


@register.filter(name="status_color")
def status_color(status):
    """Map sample status to CSS color class."""
    colors = {
        "RECEIVED": "info",
        "TESTING": "warn",
        "ANALYSIS": "warn",
        "REPORT_PREP": "brand",
        "REPORT_READY": "ok",
        "REPORT_SENT": "ok",
        "REJECTED": "danger",
    }
    return colors.get(status, "info")

@register.filter(name="feature")
def feature_filter(key):
    """Template filter to safely check feature flags: {% if 'module.batches'|feature %}...{% endif %}"""
    from apps.core.models import flag_enabled
    return flag_enabled(key)