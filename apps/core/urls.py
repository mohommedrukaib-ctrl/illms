
from django.urls import path
from . import views, views_workflow, views_molecular

"""
Core Application URL Routing

Contains all routes for:
- Dashboard, Theme toggle, Settings Hub, Recycle Bin, Documentation
- SmartSelect autocomplete endpoints
- Workflow: Clients, Samples, Status Transitions, Sample Receipts, Sample Test Attachments
- Diagnostic & Lab Tests (Culture, Chemical, Rapid, etc.)
- Molecular: Microorganism catalog, DNA extractions, PCR/qPCR assays
- Quality Control: QC Queue and Reviews
- Reports: Food Safety PDF Reports, Detection Logs, QC Compliance, Audit Export
- Reminders and Notifications
- Cryptographic Audit Trail Viewer
- User Management
- Batch Traceability Management
- Global Search
- Public Customer Portal
"""
from django.urls import path
from . import (
    views,
    views_workflow,
    views_molecular,
    views_qc,
    views_reports,
    views_reminders,
    views_audit,
    views_users,
    views_batch,
    views_search,
    views_portal,
    views_sample_test,
    views_labtest,
)


app_name = "core"

urlpatterns = [

    path("", views.dashboard_view, name="dashboard"),
    path("theme/toggle/", views.theme_toggle_view, name="theme_toggle"),
    path("settings/", views.settings_hub_view, name="settings_hub"),


    # ─── CORE PORTAL & SYSTEM SETTINGS ───
    path("", views.dashboard_view, name="dashboard"),
    path("theme/toggle/", views.theme_toggle_view, name="theme_toggle"),
    path("settings/", views.settings_hub_view, name="settings_hub"),
    path("recycle-bin/", views.recycle_bin_view, name="recycle_bin"),
    path("delete/", views.soft_delete_record, name="soft_delete"),
    path("docs/", views.documentation_view, name="documentation"),

    # ─── SMART SELECT COMPONENT ENDPOINTS ───

    path("smart/results/<str:kind_key>/", views.smart_select_results, name="smart_select_results"),
    path("smart/pick/<str:kind_key>/", views.smart_picker, name="smart_picker"),
    path("smart/demo/", views.smart_select_demo, name="smart_select_demo"),


    # Phase 4

    # ─── WORKFLOW MODULE (CLIENTS & SAMPLES) ───

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

    # ─── DIRECT SAMPLE TEST ATTACHMENT ───
    path("samples/<uuid:sample_pk>/tests/attach/", views_sample_test.SampleTestAttachView.as_view(), name="sample_test_attach"),

    # ─── DIAGNOSTIC LABORATORY TESTS (CULTURE, CHEMICAL, RAPID, ETC.) ───
    path("lab-tests/", views_labtest.LabTestListView.as_view(), name="labtest_list"),
    path("lab-tests/create/", views_labtest.LabTestCreateView.as_view(), name="labtest_create"),
    path("lab-tests/<uuid:pk>/", views_labtest.LabTestDetailView.as_view(), name="labtest_detail"),

    # ─── MOLECULAR DIAGNOSTICS MODULE ───
    path("microorganisms/", views_molecular.MicrobeListView.as_view(), name="microbe_list"),
    path("microorganisms/create/", views_molecular.MicrobeCreateView.as_view(), name="microbe_create"),
    path("dna/", views_molecular.DnaListView.as_view(), name="dna_list"),
    path("dna/create/", views_molecular.DnaCreateView.as_view(), name="dna_create"),
    path("dna/<uuid:pk>/", views_molecular.DnaDetailView.as_view(), name="dna_detail"),
    path("tests/", views_molecular.TestListView.as_view(), name="test_list"),
    path("tests/create/", views_molecular.TestCreateView.as_view(), name="test_create"),
    path("tests/<uuid:pk>/", views_molecular.TestDetailView.as_view(), name="test_detail"),

    # ─── QUALITY CONTROL & FOUR-EYES APPROVAL ───
    path("qc/", views_qc.QcQueueView.as_view(), name="qc_queue"),
    path("qc/<uuid:pk>/review/", views_qc.QcReviewView.as_view(), name="qc_review"),

    # ─── FOOD-SAFETY REPORTS & DELIVERABLES ───
    path("reports/", views_reports.ReportListView.as_view(), name="reports_list"),
    path("reports/generate/", views_reports.ReportGenerateView.as_view(), name="report_generate"),
    path("reports/<uuid:pk>/", views_reports.ReportDetailView.as_view(), name="report_detail"),
    path("reports/<uuid:pk>/download/", views_reports.ReportDownloadView.as_view(), name="report_download"),
    path("reports/<uuid:pk>/send/", views_reports.ReportSendView.as_view(), name="report_send"),
    path("reports/detections/", views_reports.DetectionLogView.as_view(), name="detection_log"),
    path("reports/qc-compliance/", views_reports.QcComplianceLogView.as_view(), name="qc_compliance_log"),
    path("reports/audit-export/", views_reports.AuditExportView.as_view(), name="audit_export"),

    # ─── ACTION REMINDERS & NOTIFICATION ALERTS ───
    path("reminders/", views_reminders.ReminderListView.as_view(), name="reminders_list"),
    path("reminders/<uuid:pk>/<str:action>/", views_reminders.ReminderActionView.as_view(), name="reminder_action"),
    path("notifications/", views_reminders.NotificationListView.as_view(), name="notifications_list"),
    path("notifications/read/", views_reminders.NotificationMarkReadView.as_view(), name="notification_mark_read"),
    path("notifications/poll/", views_reminders.NotificationPollView.as_view(), name="notification_poll"),

    # ─── IMMUTABLE CRYPTOGRAPHIC AUDIT TRAIL ───
    path("audit/", views_audit.AuditListView.as_view(), name="audit_list"),
    path("audit/<uuid:pk>/", views_audit.AuditDetailModalView.as_view(), name="audit_detail"),
    path("audit/verify/", views_audit.AuditVerifyIntegrityView.as_view(), name="audit_verify"),

        # ─── USER DIRECTORY & ACCESS CONTROL ───
    path("users/", views_users.UserListView.as_view(), name="users_list"),
    path("users/create/", views_users.UserCreateView.as_view(), name="user_create"),
    path("users/<uuid:pk>/toggle/", views_users.UserToggleActiveView.as_view(), name="user_toggle"),
    path("users/<uuid:pk>/reset-password/", views_users.UserResetPasswordView.as_view(), name="user_reset_password"),
    path("users/roles/", views_users.RoleListView.as_view(), name="roles_list"),
    path("users/roles/create/", views_users.RoleCreateView.as_view(), name="role_create"),
    path("users/roles/<uuid:pk>/delete/", views_users.RoleDeleteView.as_view(), name="role_delete"),
    # ─── BATCH MANAGEMENT & TRACEABILITY ───
    path("batches/", views_batch.BatchListView.as_view(), name="batch_list"),
    path("batches/create/", views_batch.BatchCreateView.as_view(), name="batch_create"),
    path("batches/<uuid:pk>/", views_batch.BatchDetailView.as_view(), name="batch_detail"),

    # ─── GLOBAL SEARCH ───
    path("search/", views_search.GlobalSearchView.as_view(), name="global_search"),

    # ─── PUBLIC CUSTOMER PORTAL (UNAUTHENTICATED) ───
    path("portal/", views_portal.CustomerPortalView.as_view(), name="customer_portal"),
    path("portal/api/", views_portal.CustomerTrackingAPI.as_view(), name="customer_portal_api"),
    path("portal/download/<str:tracking_code>/", views_portal.CustomerReportDownloadView.as_view(), name="customer_portal_download"),
    path("lab-tests/create/", views_labtest.LabTestCreateView.as_view(), name="labtest_create"),


]