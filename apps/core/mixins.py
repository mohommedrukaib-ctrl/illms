"""Reusable view mixins for ILIMS."""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string


class ILIMSViewMixin(LoginRequiredMixin):
    """Base mixin that adds common page context."""

    page_title = ""
    page_subtitle = ""
    page_icon = ""
    breadcrumbs = []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.page_title
        context["page_subtitle"] = self.page_subtitle
        context["page_icon"] = self.page_icon
        context["breadcrumbs"] = self.breadcrumbs
        return context


class HtmxModalMixin:
    """
    Class-based-view / function-view helper.

    Behavior:
      - If the request is HTMX AND `ui.modals` flag is enabled:
          -> render the modal fragment (partial template).
      - Otherwise:
          -> render the full standalone page (same form) that redirects
             to `?next=` upon success.

    Both paths must call the SAME form class and the SAME success handler.

    Usage:
        class ClientCreateView(HtmxModalMixin, LoginRequiredMixin, View):
            modal_template = "clients/_modal_create.html"
            page_template  = "clients/create.html"
            form_class     = ClientForm
            success_url_name = "clients:list"
    """
    modal_template = ""
    page_template = ""
    modal_title = ""

    def _is_modal(self, request):
        from apps.core.models import flag_enabled
        is_htmx = getattr(request, "htmx", False)
     # django-htmx sets request.htmx to an HtmxDetails object (truthy) or False
        if hasattr(is_htmx, "request"):
            is_htmx = True
        return bool(is_htmx) and flag_enabled("ui.modals") and request.GET.get("modal") != "0"


    def render_modal_or_page(self, request, context, status=200):
        context.setdefault("modal_title", self.modal_title)
        template = self.modal_template if self._is_modal(request) else self.page_template
        return render(request, template, context, status=status)

    def htmx_close_modal_with_toast(
        self, message="Saved.", level="success", refresh_target=None
    ):
        """
        Return HTMX response that:
          - clears #modal-host (out-of-band swap)
          - pushes a toast (out-of-band swap into #toast-host)
          - optionally triggers a refresh event on the parent page.
        """
        toast_html = render_to_string(
            "partials/_toast.html",
            {"message": message, "level": level, "oob": True},
        )
        modal_clear = '<div id="modal-host" hx-swap-oob="innerHTML"></div>'
        body = modal_clear + toast_html
        response = HttpResponse(body)
        if refresh_target:
            response["HX-Trigger"] = f'{{"ilims:refresh":"{refresh_target}"}}'
        return response 