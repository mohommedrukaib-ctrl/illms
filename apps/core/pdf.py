"""
PDF report generation using ReportLab.
Produces branded, decision-support Food Safety & Diagnostic Analysis Reports.
Includes attached lab tests, QC approvals, safety interpretations, and signatures.
"""
import io
from django.conf import settings
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _get_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ILIMSTitle", parent=styles["Title"], fontSize=20, leading=24,
        textColor=colors.HexColor("#0f9b8e"), spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="ILIMSSubtitle", parent=styles["Normal"], fontSize=10,
        textColor=colors.HexColor("#5a6775"), spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="ILIMSHeading", parent=styles["Heading2"], fontSize=12, leading=16,
        textColor=colors.HexColor("#0d6f77"), spaceBefore=12, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="ILIMSBody", parent=styles["Normal"], fontSize=9, leading=13,
        textColor=colors.HexColor("#1a2332"),
    ))
    styles.add(ParagraphStyle(
        name="ILIMSSmall", parent=styles["Normal"], fontSize=8, leading=11,
        textColor=colors.HexColor("#8899aa"),
    ))
    return styles


def _make_table(data, col_widths=None):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f9b8e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e6ea")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def generate_food_safety_report(report_obj):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )
    styles = _get_styles()
    story = []

    sample = report_obj.sample
    client = report_obj.client

    org_name = "ILIMS Laboratory Corporation"
    try:
        from apps.core.models import SystemSetting
        settings_obj = SystemSetting.get_settings()
        if settings_obj and settings_obj.organization_name:
            org_name = settings_obj.organization_name
    except Exception:
        pass

    # Header
    story.append(Paragraph(org_name, styles["ILIMSTitle"]))
    story.append(Paragraph("Food Safety & Laboratory Analysis Report", styles["ILIMSSubtitle"]))
    story.append(Spacer(1, 4))

    # Metadata
    meta_data = [
        ["Report Code", report_obj.code],
        ["Sample Code", sample.code],
        ["Tracking ID", sample.tracking_code or "N/A"],
        ["Client Name", client.name],
        ["Product / Specimen", sample.product_name],
        ["Received Date", sample.received_date.strftime("%d %B %Y") if sample.received_date else "—"],
        ["Report Issue Date", timezone.now().strftime("%d %B %Y")],
        ["Safety Classification", report_obj.get_safety_class_display()],
    ]
    story.append(Paragraph("General Specimen & Report Information", styles["ILIMSHeading"]))
    story.append(_make_table(meta_data, col_widths=[5 * cm, 11.4 * cm]))
    story.append(Spacer(1, 8))

    # Tests
    attached_tests = sample.attached_tests.filter(is_deleted=False).select_related("test_type", "operator")
    if attached_tests.exists():
        story.append(Paragraph("Laboratory Test Results", styles["ILIMSHeading"]))
        test_data = [["Test Name", "Outcome / Result", "Details / Value", "Date"]]
        for t in attached_tests:
            test_data.append([
                t.test_type.name,
                t.get_result_outcome_display(),
                t.result_value or "—",
                t.test_date.strftime("%Y-%m-%d"),
            ])
        story.append(_make_table(test_data, col_widths=[5.5 * cm, 4 * cm, 4.4 * cm, 2.5 * cm]))
        story.append(Spacer(1, 8))

    # Interpretation
    story.append(Paragraph("Food Safety Interpretation", styles["ILIMSHeading"]))
    if report_obj.safety_class == "SAFE":
        interpretation = "Based on the laboratory test results and independent QC verification, all parameters are within permissible regulatory limits. The sample is classified as SAFE."
    elif report_obj.safety_class == "UNSAFE":
        interpretation = "Laboratory analysis has identified parameters exceeding regulatory limits. The sample is classified as UNSAFE. Immediate containment or corrective measures are advised."
    else:
        interpretation = "Test results are borderline or inconclusive. Further review is required."
    story.append(Paragraph(interpretation, styles["ILIMSBody"]))
    story.append(Spacer(1, 8))

    # Signatures
    story.append(Spacer(1, 40))
    qc_record = sample.qc_records.filter(decision="APPROVED").select_related("reviewer").first()
    
    # Two-column signature block
    sig_data = [
        ["_" * 35, "_" * 35],
        [
            report_obj.generated_by.get_full_name() if report_obj.generated_by else "System Generated",
            qc_record.reviewer.get_full_name() if (qc_record and qc_record.reviewer) else "Awaiting Authorization"
        ],
        [
            "Report Prepared By",
            f"Verified & Approved By (QC Officer)\n{qc_record.reviewed_at.strftime('%d %B %Y') if qc_record and qc_record.reviewed_at else ''}"
        ]
    ]
    
    sig_table = Table(sig_data, colWidths=[8.2 * cm, 8.2 * cm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica'),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.HexColor("#5a6775")),
        ('TOPPADDING', (0, 1), (-1, 1), 6),
    ]))
    story.append(sig_table)

    doc.build(story)
    buf.seek(0)
    return buf