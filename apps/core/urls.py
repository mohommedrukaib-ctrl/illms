from django.urls import path
from . import views, views_workflow, views_molecular

app_name = "core"

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("theme/toggle/", views.theme_toggle_view, name="theme_toggle"),
    path("settings/", views.settings_hub_view, name="settings_hub"),

    path("smart/results/<str:kind_key>/", views.smart_select_results, name="smart_select_results"),
    path("smart/pick/<str:kind_key>/", views.smart_picker, name="smart_picker"),
    path("smart/demo/", views.smart_select_demo, name="smart_select_demo"),

    # Phase 4
    path("clients/", views_workflow.ClientListView.as_view(), name="client_list"),
    path("clients/create/", views_workflow.ClientCreateView.as_view(), name="client_create"),
    path("samples/", views_workflow.SampleListView.as_view(), name="sample_list"),
    path("samples/create/", views_workflow.SampleCreateView.as_view(), name="sample_create"),
    path("samples/<uuid:pk>/", views_workflow.SampleDetailView.as_view(), name="sample_detail"),
    path("samples/<uuid:pk>/receipt/", views_workflow.SampleReceiptView.as_view(), name="sample_receipt"),
    path("samples/<uuid:pk>/advance/", views_workflow.SampleAdvanceStatusView.as_view(), name="sample_advance"),

    # Phase 5 — Molecular
    path("microorganisms/", views_molecular.MicrobeListView.as_view(), name="microbe_list"),
    path("microorganisms/create/", views_molecular.MicrobeCreateView.as_view(), name="microbe_create"),

    path("dna/", views_molecular.DnaListView.as_view(), name="dna_list"),
    path("dna/create/", views_molecular.DnaCreateView.as_view(), name="dna_create"),
    path("dna/<uuid:pk>/", views_molecular.DnaDetailView.as_view(), name="dna_detail"),
    path("delete/", views.soft_delete_record, name="soft_delete"),
    path("tests/", views_molecular.TestListView.as_view(), name="test_list"),
    path("tests/create/", views_molecular.TestCreateView.as_view(), name="test_create"),
    path("tests/<uuid:pk>/", views_molecular.TestDetailView.as_view(), name="test_detail"),
]