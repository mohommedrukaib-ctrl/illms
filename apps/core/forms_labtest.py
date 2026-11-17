from django import forms
from apps.core.models import LabTest
from apps.core.widgets import SmartModelChoiceField, SmartSelect


class LabTestForm(forms.ModelForm):
    sample_code = forms.CharField(
        label="Sample",
        required=True,
        widget=SmartSelect(kind_key="sample", allow_create=True),
    )
    test_type_name = forms.CharField(
        label="Test Method / Name",
        required=False,
        widget=SmartSelect(kind_key="lab_method", allow_create=False),
        help_text="Select a registered test method or type a name.",
    )
    target_name = forms.CharField(
        label="Target Organism (if applicable)",
        required=False,
        widget=SmartSelect(kind_key="microorganism", allow_create=True),
    )
    operator = SmartModelChoiceField(
        kind_key="user", allow_create=False, required=False,
    )

    class Meta:
        model = LabTest
        fields = [
            "method_name", "run_date", "operator", "instrument",
            "detection", "result_value", "result_unit", "limit_value",
            "status", "notes",
        ]
        widgets = {
            "method_name": forms.TextInput(attrs={"class": "form-input"}),
            "run_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "instrument": forms.TextInput(attrs={"class": "form-input"}),
            "detection": forms.Select(attrs={"class": "form-input"}),
            "result_value": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. 1500"}),
            "result_unit": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. CFU/g, ppm, %"}),
            "limit_value": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. <1000"}),
            "status": forms.Select(attrs={"class": "form-input"}),
            "notes": forms.Textarea(attrs={"class": "form-textarea", "rows": 2}),
        }

    def __init__(self, *args, next_url="", current_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ["sample_code", "test_type_name", "target_name", "operator"]:
            if f in self.fields:
                self.fields[f].widget.next_url = next_url
                self.fields[f].widget.attrs.setdefault("id", f"id_{f}")

        if current_user and current_user.is_authenticated and not self.initial.get("operator"):
            self.fields["operator"].initial = current_user.pk
            self.fields["operator"].widget.attrs["data-prefill-display"] = current_user.get_full_name()