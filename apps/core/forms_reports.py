from django import forms
from apps.core.models import Report, QcRecord


class ReportGenerateForm(forms.ModelForm):
    """Form to generate or update a food-safety report."""

    class Meta:
        model = Report
        fields = ["safety_class", "summary"]
        widgets = {
            "safety_class": forms.Select(attrs={"class": "form-input"}),
            "summary": forms.Textarea(
                attrs={
                    "class": "form-textarea",
                    "rows": 4,
                    "placeholder": "Optional notes for the report…",
                }
            ),
        }

    def clean_safety_class(self):
        val = self.cleaned_data.get("safety_class")
        if val == "NOT_APPLICABLE":
            raise forms.ValidationError("Select a safety classification before generating the report.")
        return val


class ReportSendForm(forms.Form):
    """Form to send a report via email."""
    recipient_email = forms.EmailField(
        label="Recipient Email",
        widget=forms.EmailInput(attrs={
            "class": "form-input",
            "placeholder": "client@example.com",
        }),
    )
    message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-textarea",
            "rows": 3,
            "placeholder": "Optional message to include in the email…",
        }),
    )