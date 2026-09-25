from django import forms
from django.forms import inlineformset_factory

from apps.core.models import DnaExtraction, Microorganism, MolecularTest, TestResult
from apps.core.widgets import SmartModelChoiceField, SmartSelect


class MicroorganismForm(forms.ModelForm):
    category_name = forms.CharField(
        label="Category",
        required=False,
        widget=SmartSelect(kind_key="product_category", allow_create=False),
        help_text="Select existing (e.g., Bacteria, Virus).",
    )
    risk_name = forms.CharField(
        label="Risk Level",
        required=False,
        widget=SmartSelect(kind_key="risk_level", allow_create=False),
    )

    class Meta:
        model = Microorganism
        fields = ["name", "scientific_name", "code", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-input"}),
            "scientific_name": forms.TextInput(attrs={"class": "form-input"}),
            "code": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. SALM"}),
            "description": forms.Textarea(attrs={"class": "form-textarea", "rows": 2}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, next_url="", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category_name"].widget.next_url = next_url
        self.fields["category_name"].widget.attrs["id"] = "id_category_name"
        self.fields["risk_name"].widget.next_url = next_url
        self.fields["risk_name"].widget.attrs["id"] = "id_risk_name"

    def clean_code(self):
        return (self.cleaned_data.get("code") or "").strip().upper()

    def clean_name(self):
        return (self.cleaned_data.get("name") or "").strip()


class DnaExtractionForm(forms.ModelForm):
    sample_code = forms.CharField(
        label="Sample",
        required=True,
        widget=SmartSelect(kind_key="sample", allow_create=True),
    )
    method_name = forms.CharField(
        label="Extraction Method",
        required=False,
        widget=SmartSelect(kind_key="lab_method", allow_create=False),
        help_text="Select from registered extraction methods only.",
    )
    operator = SmartModelChoiceField(kind_key="user", allow_create=False, required=False)

    class Meta:
        model = DnaExtraction
        fields = [
            "kit_name", "extraction_date", "operator",
            "concentration_ng_ul", "purity_260_280", "purity_260_230",
            "volume_ul", "notes",
        ]
        widgets = {
            "kit_name": forms.TextInput(attrs={"class": "form-input"}),
            "extraction_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "concentration_ng_ul": forms.NumberInput(attrs={"class": "form-input", "step": "0.001"}),
            "purity_260_280": forms.NumberInput(attrs={"class": "form-input", "step": "0.001"}),
            "purity_260_230": forms.NumberInput(attrs={"class": "form-input", "step": "0.001"}),
            "volume_ul": forms.NumberInput(attrs={"class": "form-input", "step": "0.01"}),
            "notes": forms.Textarea(attrs={"class": "form-textarea", "rows": 2}),
        }

    def __init__(self, *args, next_url="", hide_advanced=False, current_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sample_code"].widget.next_url = next_url
        self.fields["sample_code"].widget.attrs["id"] = "id_sample_code"
        self.fields["method_name"].widget.next_url = next_url
        self.fields["method_name"].widget.attrs["id"] = "id_method_name"
        self.fields["operator"].widget.next_url = next_url

        # Auto-default operator to logged-in user
        if current_user and current_user.is_authenticated and not self.initial.get("operator"):
            self.fields["operator"].initial = current_user.pk
            self.fields["operator"].widget.attrs["data-prefill-display"] = current_user.get_full_name()

        if hide_advanced:
            for f in ("concentration_ng_ul", "purity_260_280", "purity_260_230", "volume_ul"):
                self.fields.pop(f, None)


class MolecularTestForm(forms.ModelForm):
    sample_code = forms.CharField(
        label="Sample",
        required=True,
        widget=SmartSelect(kind_key="sample", allow_create=True),
    )
    dna_extraction = SmartModelChoiceField(kind_key="dna_extraction", allow_create=False, required=False)
    test_type_name = forms.CharField(
        label="Test Type / Method",
        required=False,
        widget=SmartSelect(kind_key="lab_method", allow_create=False),
        help_text="Select a registered test method (PCR, qPCR, Sequencing).",
    )
    target_name = forms.CharField(
        label="Primary Target",
        required=False,
        widget=SmartSelect(kind_key="microorganism", allow_create=True),
        help_text="Select from catalog, or type a new microorganism name to add it.",
    )
    operator = SmartModelChoiceField(kind_key="user", allow_create=False, required=False)

    class Meta:
        model = MolecularTest
        fields = [
            "dna_extraction", "assay_name", "run_date", "operator", "instrument",
            "ct_value", "ct_cutoff", "slope", "r_squared", "sequence_id", "read_length", "notes",
        ]
        widgets = {
            "assay_name": forms.TextInput(attrs={"class": "form-input"}),
            "run_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "instrument": forms.TextInput(attrs={"class": "form-input"}),
            "ct_value": forms.NumberInput(attrs={"class": "form-input", "step": "0.001"}),
            "ct_cutoff": forms.NumberInput(attrs={"class": "form-input", "step": "0.001"}),
            "slope": forms.NumberInput(attrs={"class": "form-input", "step": "0.0001"}),
            "r_squared": forms.NumberInput(attrs={"class": "form-input", "step": "0.0001"}),
            "sequence_id": forms.TextInput(attrs={"class": "form-input"}),
            "read_length": forms.NumberInput(attrs={"class": "form-input"}),
            "notes": forms.Textarea(attrs={"class": "form-textarea", "rows": 2}),
        }

    def __init__(self, *args, next_url="", hide_advanced=False, current_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ["sample_code", "dna_extraction", "test_type_name", "target_name", "operator"]:
            if f in self.fields:
                self.fields[f].widget.next_url = next_url
                self.fields[f].widget.attrs["id"] = f"id_{f}"

        if current_user and current_user.is_authenticated and not self.initial.get("operator"):
            self.fields["operator"].initial = current_user.pk
            self.fields["operator"].widget.attrs["data-prefill-display"] = current_user.get_full_name()

        if hide_advanced:
            for f in ("ct_value", "ct_cutoff", "slope", "r_squared", "sequence_id", "read_length", "dna_extraction"):
                self.fields.pop(f, None)


class TestResultForm(forms.ModelForm):
    microorganism = SmartModelChoiceField(kind_key="microorganism", allow_create=True)

    class Meta:
        model = TestResult
        fields = ["microorganism", "detection", "ct_value", "gene_target", "notes"]
        widgets = {
            "detection": forms.Select(attrs={"class": "form-input"}),
            "ct_value": forms.NumberInput(attrs={"class": "form-input", "step": "0.001"}),
            "gene_target": forms.TextInput(attrs={"class": "form-input"}),
            "notes": forms.TextInput(attrs={"class": "form-input"}),
        }


TestResultFormSet = inlineformset_factory(
    MolecularTest, TestResult, form=TestResultForm,
    extra=2, can_delete=True,
    fields=["microorganism", "detection", "ct_value", "gene_target", "notes"],
)