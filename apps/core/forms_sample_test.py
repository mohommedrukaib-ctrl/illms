from django import forms
from apps.core.models import LabMethod, SampleTest
from apps.core.widgets import SmartModelChoiceField, SmartSelect


class SampleTestForm(forms.ModelForm):
    test_type_name = forms.CharField(
        label="Test Name / Type",
        required=True,
        widget=SmartSelect(kind_key="lab_method", allow_create=True),
        help_text="Select existing or type any new test name directly (e.g. DENGUE NS1, SALMONELLA, HEAVY METALS).",
    )
    operator = SmartModelChoiceField(
        kind_key="user", allow_create=False, required=False, label="Lab Technician / Analyst"
    )

    class Meta:
        model = SampleTest
        fields = [
            "result_outcome", "result_value", "test_date",
            "operator", "attachment", "notes",
        ]
        widgets = {
            "result_outcome": forms.Select(attrs={
                "class": "form-input",
                "style": "height: 36px; padding: 4px 8px; font-size: 0.875rem; width: 100%;",
            }),
            "result_value": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g. Reactive, 1500 CFU/g, Titer 1:80",
                "style": "height: 36px; padding: 4px 8px; font-size: 0.875rem; width: 100%;",
            }),
            "test_date": forms.DateInput(attrs={
                "class": "form-input",
                "type": "date",
                "style": "height: 36px; padding: 4px 8px; font-size: 0.875rem;",
            }),
            "attachment": forms.FileInput(attrs={"class": "form-input"}),
            "notes": forms.Textarea(attrs={"class": "form-textarea", "rows": 2}),
        }

    def __init__(self, *args, next_url="", current_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if "test_type_name" in self.fields:
            self.fields["test_type_name"].widget.next_url = next_url
            self.fields["test_type_name"].widget.attrs.setdefault("id", "id_test_type_name")
            self.fields["test_type_name"].widget.attrs["oninput"] = "this.value = this.value.toUpperCase()"

        if "operator" in self.fields:
            self.fields["operator"].widget.next_url = next_url
            self.fields["operator"].widget.attrs.setdefault("id", "id_operator")

        if self.instance and self.instance.pk and getattr(self.instance, "test_type_id", None):
            self.initial["test_type_name"] = self.instance.test_type.name

        if current_user and current_user.is_authenticated and not self.initial.get("operator"):
            self.fields["operator"].initial = current_user.pk
            self.fields["operator"].widget.attrs["data-prefill-display"] = current_user.get_full_name()

    def clean_test_type_name(self):
        name = (self.cleaned_data.get("test_type_name") or "").strip().upper()
        if not name:
            raise forms.ValidationError("Please specify a test name.")
        return name