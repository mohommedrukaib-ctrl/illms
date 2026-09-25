from django import forms
from apps.core.models import Country, Region, Laboratory, SystemSetting


class CountryForm(forms.ModelForm):
    class Meta:
        model = Country
        fields = ["name", "iso2", "iso3", "dial_code", "currency", "timezone", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-input"}),
            "iso2": forms.TextInput(attrs={"class": "form-input", "placeholder": "US"}),
            "iso3": forms.TextInput(attrs={"class": "form-input", "placeholder": "USA"}),
            "dial_code": forms.TextInput(attrs={"class": "form-input", "placeholder": "+1"}),
            "currency": forms.TextInput(attrs={"class": "form-input", "placeholder": "USD"}),
            "timezone": forms.TextInput(attrs={"class": "form-input", "placeholder": "America/New_York"}),
        }


class RegionForm(forms.ModelForm):
    class Meta:
        model = Region
        fields = ["country", "code", "name", "is_active"]
        widgets = {
            "country": forms.Select(attrs={"class": "form-select"}),
            "code": forms.TextInput(attrs={"class": "form-input", "placeholder": "CA"}),
            "name": forms.TextInput(attrs={"class": "form-input", "placeholder": "California"}),
        }


class LaboratoryForm(forms.ModelForm):
    class Meta:
        model = Laboratory
        fields = ["code", "name", "country", "region", "address", "phone", "email", "is_active"]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-input", "placeholder": "LAB-01"}),
            "name": forms.TextInput(attrs={"class": "form-input"}),
            "country": forms.Select(attrs={"class": "form-select"}),
            "region": forms.Select(attrs={"class": "form-select"}),
            "address": forms.Textarea(attrs={"class": "form-textarea", "rows": 2}),
            "phone": forms.TextInput(attrs={"class": "form-input"}),
            "email": forms.EmailInput(attrs={"class": "form-input"}),
        }


class SystemSettingsForm(forms.ModelForm):
    # Flatten numbering and SLA configs for easy form submission
    client_prefix = forms.CharField(max_length=10, required=True, widget=forms.TextInput(attrs={"class": "form-input"}))
    sample_prefix = forms.CharField(max_length=10, required=True, widget=forms.TextInput(attrs={"class": "form-input"}))
    batch_prefix = forms.CharField(max_length=10, required=True, widget=forms.TextInput(attrs={"class": "form-input"}))
    report_prefix = forms.CharField(max_length=10, required=True, widget=forms.TextInput(attrs={"class": "form-input"}))
    separator = forms.CharField(max_length=2, required=True, widget=forms.TextInput(attrs={"class": "form-input"}))
    padding = forms.IntegerField(min_value=3, max_value=10, widget=forms.TextInput(attrs={"class": "form-input", "type": "number"}))
    reset_yearly = forms.BooleanField(required=False)

    tat_normal_days = forms.IntegerField(min_value=1, widget=forms.TextInput(attrs={"class": "form-input", "type": "number"}))
    tat_urgent_days = forms.IntegerField(min_value=1, widget=forms.TextInput(attrs={"class": "form-input", "type": "number"}))
    working_days_only = forms.BooleanField(required=False)

    class Meta:
        model = SystemSetting
        fields = ["organization_name"]
        widgets = {
            "organization_name": forms.TextInput(attrs={"class": "form-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            num = self.instance.numbering_settings
            sla = self.instance.sla_settings
            
            self.fields["client_prefix"].initial = num.get("client_prefix", "CUS")
            self.fields["sample_prefix"].initial = num.get("sample_prefix", "FS")
            self.fields["batch_prefix"].initial = num.get("batch_prefix", "BAT")
            self.fields["report_prefix"].initial = num.get("report_prefix", "RPT")
            self.fields["separator"].initial = num.get("separator", "-")
            self.fields["padding"].initial = num.get("padding", 5)
            self.fields["reset_yearly"].initial = num.get("reset_yearly", True)

            self.fields["tat_normal_days"].initial = sla.get("tat_normal_days", 5)
            self.fields["tat_urgent_days"].initial = sla.get("tat_urgent_days", 2)
            self.fields["working_days_only"].initial = sla.get("working_days_only", True)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.numbering_settings = {
            "client_prefix": self.cleaned_data["client_prefix"],
            "sample_prefix": self.cleaned_data["sample_prefix"],
            "batch_prefix": self.cleaned_data["batch_prefix"],
            "report_prefix": self.cleaned_data["report_prefix"],
            "separator": self.cleaned_data["separator"],
            "padding": self.cleaned_data["padding"],
            "reset_yearly": self.cleaned_data["reset_yearly"],
        }
        instance.sla_settings = {
            "tat_normal_days": self.cleaned_data["tat_normal_days"],
            "tat_urgent_days": self.cleaned_data["tat_urgent_days"],
            "working_days_only": self.cleaned_data["working_days_only"],
        }
        if commit:
            instance.save()
        return instance