"""
SmartSelect registry, resolver mixin, and dataclass definitions.
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional
from django.db.models import Q, QuerySet
from apps.core.models import RiskLevel


@dataclass
class SmartKind:
    key: str
    label: str
    queryset_fn: Callable[[], QuerySet]
    search_fields: List[str]
    display_fn: Callable[[object], str]
    code_fn: Callable[[object], str] = field(default=lambda o: "")
    sub_fn: Callable[[object], str] = field(default=lambda o: "")
    value_fn: Callable[[object], str] = field(default=lambda o: str(o.pk))
    create_url_name: Optional[str] = None
    permission_check: Optional[Callable] = None
    max_results: int = 20


class SmartRegistry:
    _kinds: dict = {}

    @classmethod
    def register(cls, kind: SmartKind):
        cls._kinds[kind.key] = kind
        return kind

    @classmethod
    def get(cls, key: str) -> Optional[SmartKind]:
        return cls._kinds.get(key)

    @classmethod
    def all(cls) -> dict:
        return dict(cls._kinds)


def smart_search(kind: SmartKind, query: str, limit: Optional[int] = None) -> QuerySet:
    qs = kind.queryset_fn()
    query = (query or "").strip()

    if query:
        q_obj = Q()
        for fname in kind.search_fields:
            q_obj |= Q(**{f"{fname}__icontains": query})
        qs = qs.filter(q_obj)

    return qs[: (limit or kind.max_results)]


def smart_resolve(kind: SmartKind, typed_text: str):
    typed = (typed_text or "").strip()
    if not typed:
        return ("empty", None, "", kind.queryset_fn().none())

    qs = smart_search(kind, typed, limit=10)
    exact_matches = [
        obj for obj in qs if kind.display_fn(obj).strip().lower() == typed.lower()
    ]

    if len(exact_matches) == 1:
        return ("resolved", exact_matches[0].pk, "", qs)
    if len(exact_matches) > 1:
        return (
            "ambiguous",
            None,
            f"Multiple '{kind.label}' entries match '{typed}'. Please select one.",
            qs,
        )

    if qs.exists() and qs.count() == 1:
        obj = qs.first()
        return ("resolved", obj.pk, "", qs)

    if qs.exists():
        return (
            "ambiguous",
            None,
            f"Several '{kind.label}' entries partially match '{typed}'. Refine or select one.",
            qs,
        )

    return (
        "not_found",
        None,
        f"No '{kind.label}' matches '{typed}'.",
        qs,
    )


def _register_all():
    from apps.core.models import (
        Country, Region, Laboratory, Client, Sample,
        ProductCategory, ProductType, WorkflowStatus, LabMethod,
        Microorganism, DnaExtraction
    )
    from django.contrib.auth import get_user_model
    User = get_user_model()

    SmartRegistry.register(SmartKind(
        key="country",
        label="Country",
        queryset_fn=lambda: Country.objects.filter(is_active=True).order_by("name"),
        search_fields=["name", "iso2", "iso3"],
        display_fn=lambda o: o.name,
        code_fn=lambda o: o.iso2,
        sub_fn=lambda o: f"{o.iso3} · {o.timezone}",
    ))

    SmartRegistry.register(SmartKind(
        key="region",
        label="Region",
        queryset_fn=lambda: Region.objects.filter(is_active=True).select_related("country").order_by("name"),
        search_fields=["name", "code", "country__name"],
        display_fn=lambda o: o.name,
        code_fn=lambda o: o.code,
        sub_fn=lambda o: o.country.name,
    ))

    SmartRegistry.register(SmartKind(
        key="laboratory",
        label="Laboratory",
        queryset_fn=lambda: Laboratory.objects.filter(is_active=True, is_deleted=False).select_related("country", "region").order_by("name"),
        search_fields=["name", "code", "country__name", "region__name"],
        display_fn=lambda o: o.name,
        code_fn=lambda o: o.code,
        sub_fn=lambda o: f"{o.region.name if o.region else ''}, {o.country.name}".strip(", "),
    ))

    SmartRegistry.register(SmartKind(
        key="client",
        label="Client",
        queryset_fn=lambda: Client.objects.filter(is_active=True, is_deleted=False).select_related("country").order_by("name"),
        search_fields=["name", "code", "email", "phone"],
        display_fn=lambda o: o.name,
        code_fn=lambda o: o.code,
        sub_fn=lambda o: o.phone or o.email or (o.country.name if o.country else ""),
        create_url_name="core:client_create",
    ))

    SmartRegistry.register(SmartKind(
        key="user",
        label="Technician / User",
        queryset_fn=lambda: User.objects.filter(is_active=True, is_deleted=False).order_by("first_name"),
        search_fields=["first_name", "last_name", "email", "username"],
        display_fn=lambda o: o.get_full_name(),
        sub_fn=lambda o: o.get_role_display(),
    ))

    SmartRegistry.register(SmartKind(
        key="product_category",
        label="Product Category",
        queryset_fn=lambda: ProductCategory.objects.filter(is_deleted=False, is_active=True).order_by("name"),
        search_fields=["name"],
        display_fn=lambda o: o.name,
    ))

    SmartRegistry.register(SmartKind(
        key="product_type",
        label="Product Type",
        queryset_fn=lambda: ProductType.objects.filter(is_deleted=False, is_active=True).select_related("category").order_by("name"),
        search_fields=["name", "category__name"],
        display_fn=lambda o: o.name,
        sub_fn=lambda o: o.category.name if o.category else "",
    ))

    SmartRegistry.register(SmartKind(
        key="workflow_status",
        label="Status",
        queryset_fn=lambda: WorkflowStatus.objects.filter(is_active=True).order_by("order", "name"),
        search_fields=["name"],
        display_fn=lambda o: o.name,
    ))

    SmartRegistry.register(SmartKind(
        key="lab_method",
        label="Method / Test Type",
        queryset_fn=lambda: LabMethod.objects.filter(is_deleted=False, is_active=True).order_by("name"),
        search_fields=["name", "category"],
        display_fn=lambda o: o.name,
        sub_fn=lambda o: o.category,
    ))

    SmartRegistry.register(SmartKind(
        key="sample",
        label="Sample",
        queryset_fn=lambda: Sample.objects.filter(is_deleted=False).select_related("client").order_by("-created_at"),
        search_fields=["code", "product_name", "client__name"],
        display_fn=lambda o: o.code,
        code_fn=lambda o: o.client.name if o.client_id else "",
        sub_fn=lambda o: f"{o.product_name} · {o.status.name if o.status else ''}",
        create_url_name="core:sample_create",  # <-- ADD THIS LINE
    ))

    SmartRegistry.register(SmartKind(
        key="microorganism",
        label="Microorganism",
        queryset_fn=lambda: Microorganism.objects.filter(is_active=True, is_deleted=False).order_by("name"),
        search_fields=["name", "scientific_name", "code"],
        display_fn=lambda o: o.name,
        code_fn=lambda o: o.code,
        sub_fn=lambda o: o.scientific_name or "",
        create_url_name="core:microbe_create",
    ))

    SmartRegistry.register(SmartKind(
        key="dna_extraction",
        label="DNA Extraction",
        queryset_fn=lambda: DnaExtraction.objects.filter(is_deleted=False).select_related("sample").order_by("-extraction_date"),
        search_fields=["code", "sample__code", "kit_name"],
        display_fn=lambda o: o.code,
        code_fn=lambda o: o.sample.code if o.sample_id else "",
        sub_fn=lambda o: f"{o.method.name if o.method else ''} · {o.status.name if o.status else ''}",
    ))

   
    SmartRegistry.register(SmartKind(
        key="risk_level",
        label="Risk Level",
        queryset_fn=lambda: RiskLevel.objects.filter(is_active=True).order_by("severity"),
        search_fields=["name"],
        display_fn=lambda o: o.name,
    ))


_register_all()