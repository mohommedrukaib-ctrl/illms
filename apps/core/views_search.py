from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import render
from django.views import View

from apps.core.models import (
    Client, FoodBatch, Microorganism, MolecularTest, Sample,
)

User = get_user_model()


class GlobalSearchView(LoginRequiredMixin, View):
    """
    Cross-model global search accessible from the topbar.
    Searches: Samples, Clients, Batches, Tests, Microorganisms, Users.
    """

    def get(self, request):
        q = request.GET.get("q", "").strip()
        results = {
            "samples": [],
            "clients": [],
            "batches": [],
            "tests": [],
            "microbes": [],
            "users": [],
        }
        total = 0

        if len(q) >= 2:
            # Samples
            samples = Sample.objects.filter(
                is_deleted=False,
            ).filter(
                Q(code__icontains=q)
                | Q(product_name__icontains=q)
                | Q(client__name__icontains=q)
            ).select_related("client")[:10]
            results["samples"] = samples
            total += samples.count()

            # Clients
            clients = Client.objects.filter(
                is_deleted=False,
            ).filter(
                Q(name__icontains=q)
                | Q(code__icontains=q)
                | Q(email__icontains=q)
                | Q(phone__icontains=q)
            )[:10]
            results["clients"] = clients
            total += clients.count()

            # Batches
            batches = FoodBatch.objects.filter(
                is_deleted=False,
            ).filter(
                Q(code__icontains=q)
                | Q(batch_number__icontains=q)
                | Q(product_name__icontains=q)
            ).select_related("client")[:10]
            results["batches"] = batches
            total += batches.count()

            # Molecular Tests
            tests = MolecularTest.objects.filter(
                is_deleted=False,
            ).filter(
                Q(code__icontains=q)
                | Q(sample__code__icontains=q)
                | Q(assay_name__icontains=q)
            ).select_related("sample")[:10]
            results["tests"] = tests
            total += tests.count()

            # Microorganisms
            microbes = Microorganism.objects.filter(
                is_deleted=False,
            ).filter(
                Q(name__icontains=q)
                | Q(code__icontains=q)
                | Q(scientific_name__icontains=q)
            )[:10]
            results["microbes"] = microbes
            total += microbes.count()

            # Users (only for admins)
            if request.user.is_superuser or request.user.role == "ADMIN":
                users = User.objects.filter(
                    is_deleted=False,
                ).filter(
                    Q(username__icontains=q)
                    | Q(email__icontains=q)
                    | Q(first_name__icontains=q)
                    | Q(last_name__icontains=q)
                )[:10]
                results["users"] = users
                total += users.count()

        return render(request, "pages/search_results.html", {
            "page_title": "Search Results",
            "page_subtitle": f"Found {total} result{'s' if total != 1 else ''} for '{q}'" if q else "Enter a search term",
            "page_icon": "search",
            "query": q,
            "results": results,
            "total": total,
        })