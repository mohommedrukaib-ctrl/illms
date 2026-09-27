from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from apps.core.audit import get_changes, log_audit
from apps.core.forms_batch import BatchForm
from apps.core.mixins import HtmxModalMixin, ILIMSViewMixin
from apps.core.models import Client, FoodBatch, next_code


def _full_reload(url):
    body = (
        f'<div id="modal-host" hx-swap-oob="innerHTML"></div>'
        f'<meta http-equiv="refresh" content="0;url={url}">'
    )
    response = HttpResponse(body, status=200)
    response["HX-Redirect"] = url
    response["HX-Trigger"] = "ilims:refresh"
    return response


class BatchListView(ILIMSViewMixin, ListView):
    model = FoodBatch
    template_name = "batch/batch_list.html"
    context_object_name = "batches"
    paginate_by = 50
    page_title = "Food Batches"
    page_subtitle = "Production batch tracking and traceability"
    page_icon = "batch"

    def get_queryset(self):
        qs = FoodBatch.objects.filter(is_deleted=False).select_related("client")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(code__icontains=q)
                | Q(batch_number__icontains=q)
                | Q(product_name__icontains=q)
                | Q(client__name__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["current_q"] = self.request.GET.get("q", "")
        return ctx

    def get_template_names(self):
        if getattr(self.request, "htmx", False) and not getattr(
            self.request.htmx, "boosted", False
        ):
            return ["batch/partials/_batch_list_rows.html"]
        return [self.template_name]


class BatchCreateView(HtmxModalMixin, LoginRequiredMixin, View):
    modal_template = "batch/partials/_modal_batch_form.html"
    page_template = "batch/batch_form_page.html"
    modal_title = "Register New Batch"

    def _get_instance(self, request):
        edit_pk = request.GET.get("edit") or request.POST.get("edit")
        if edit_pk:
            try:
                return FoodBatch.objects.get(pk=edit_pk, is_deleted=False)
            except (FoodBatch.DoesNotExist, ValueError):
                pass
        return None

    def get(self, request):
        instance = self._get_instance(request)
        title = "Edit Batch" if instance else "Register New Batch"
        next_url = request.GET.get("next", reverse("core:batch_list"))
        form = BatchForm(instance=instance, next_url=next_url)
        return self.render_modal_or_page(request, {
            "form": form, "next_url": next_url,
            "modal_title": title, "edit_pk": instance.pk if instance else "",
        })

    def post(self, request):
        instance = self._get_instance(request)
        title = "Edit Batch" if instance else "Register New Batch"
        next_url = request.POST.get("next", reverse("core:batch_list"))
        form = BatchForm(request.POST, instance=instance, next_url=next_url)

        client_pk = request.POST.get("client_name", "").strip()
        client = None
        if client_pk:
            client = Client.objects.filter(pk=client_pk, is_deleted=False).first()

        if not client and not instance:
            form.add_error("client_name", "Select a valid client.")

        if form.is_valid() and client:
            obj = form.save(commit=False)
            obj.client = client
            if not obj.pk or not obj.code:
                obj.code = next_code("BATCH", client.country, getattr(client, "region", None))
            obj.save()

            action = "UPDATE" if instance else "CREATE"
            log_audit(request.user, action, obj,
                      get_changes(instance, obj, ["batch_number", "product_name", "client_id"]))
            messages.success(request, f"Batch {obj.code} saved.")

            if self._is_modal(request):
                return _full_reload(next_url)
            return redirect(next_url)

        return self.render_modal_or_page(request, {
            "form": form, "next_url": next_url,
            "modal_title": title, "edit_pk": instance.pk if instance else "",
        }, status=400)


class BatchDetailView(ILIMSViewMixin, View):
    def get(self, request, pk):
        batch = get_object_or_404(
            FoodBatch.objects.select_related("client"),
            pk=pk, is_deleted=False,
        )
        samples = batch.samples.filter(is_deleted=False).select_related(
            "client", "product_type"
        )
        return render(request, "batch/batch_detail.html", {
            "page_title": batch.code, "page_icon": "batch",
            "batch": batch, "samples": samples,
        })