from django import forms
from apps.core.models import FoodBatch
from apps.core.widgets import SmartModelChoiceField


class BatchForm(forms.ModelForm):
    client_name = SmartModelChoiceField(
        kind_key="client", allow_create=False, label="Client"
    )

    class Meta:
        model = FoodBatch
        fields = [
            "batch_number", "product_name", "production_date",
            "expiry_date", "quantity", "storage_condition", "notes",
        ]
        widgets = {
            "batch_number": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. LOT-2026-09-A"}),
            "product_name": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Chicken Sausages"}),
            "production_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "expiry_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "quantity": forms.NumberInput(attrs={"class": "form-input", "min": "1"}),
            "storage_condition": forms.Select(attrs={"class": "form-input"}),
            "notes": forms.Textarea(attrs={"class": "form-textarea", "rows": 2}),
        }

    def __init__(self, *args, next_url="", **kwargs):
        super().__init__(*args, **kwargs)
        if "client_name" in self.fields:
            self.fields["client_name"].widget.next_url = next_url
            self.fields["client_name"].widget.attrs.setdefault("id", "id_client_name")
        self.fields["batch_number"].required = True

    def clean_batch_number(self):
        val = (self.cleaned_data.get("batch_number") or "").strip()
        if not val:
            raise forms.ValidationError("Batch number is required.")
        return val.upper()