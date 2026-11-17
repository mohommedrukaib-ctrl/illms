from django import forms
from apps.core.models import QcRecord


class QcReviewForm(forms.ModelForm):
    """Form for QC officer to record their review decision."""

    class Meta:
        model = QcRecord
        fields = ["decision", "safety_class", "review_notes"]
        widgets = {
            "decision": forms.Select(attrs={"class": "form-input"}),
            "safety_class": forms.Select(attrs={"class": "form-input"}),
            "review_notes": forms.Textarea(
                attrs={
                    "class": "form-textarea",
                    "rows": 4,
                    "placeholder": "Explain your decision, cite protocol references, note anomalies…",
                }
            ),
        }

    def clean(self):
        cleaned = super().clean()
        decision = cleaned.get("decision")
        safety = cleaned.get("safety_class")
        notes = (cleaned.get("review_notes") or "").strip()

        if decision in ("REJECTED", "REWORK") and not notes:
            self.add_error(
                "review_notes",
                "Notes are required when rejecting or requesting rework.",
            )

        if decision == "APPROVED" and safety == "NOT_APPLICABLE":
            self.add_error(
                "safety_class",
                "You must classify the sample when approving.",
            )

        return cleaned