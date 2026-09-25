from django import forms
from apps.core.models import Client, Sample
from apps.core.widgets import SmartModelChoiceField, SmartSelect


class ClientForm(forms.ModelForm):
    country = SmartModelChoiceField(kind_key="country", allow_create=False)
    region = SmartModelChoiceField(kind_key="region", allow_create=False, required=False)

    class Meta:
        model = Client
        fields = ["name", "contact_person", "email", "phone", "address", "country", "region"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Keells Foods"}),
            "contact_person": forms.TextInput(attrs={"class": "form-input"}),
            "email": forms.EmailInput(attrs={"class": "form-input"}),
            "phone": forms.TextInput(attrs={"class": "form-input"}),
            "address": forms.Textarea(attrs={"class": "form-textarea", "rows": 2}),
        }

    def __init__(self, *args, next_url="", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["country"].widget.next_url = next_url
        self.fields["region"].widget.next_url = next_url
        self.fields["name"].required = True
        self.fields["phone"].required = True
        self.fields["country"].required = True

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Client name is required.")
        return name.title()

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not phone:
            raise forms.ValidationError("Phone number is required.")
        qs = Client.objects.filter(phone=phone, is_deleted=False)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Phone '{phone}' already used by {qs.first().name}.")
        return phone


class SampleForm(forms.ModelForm):
    client_name = forms.CharField(
        label="Client Name",
        required=True,
        widget=SmartSelect(kind_key="client", allow_create=False),
    )
    client_phone = forms.CharField(
        label="Client Phone",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "e.g. +94 77 123 4567",
            "id": "id_client_phone",
            "disabled": "disabled",
        }),
    )

    product_category = forms.CharField(
        label="Category",
        required=False,
        widget=SmartSelect(kind_key="product_category", allow_create=False),
    )
    product_type = forms.CharField(
        label="Product Type",
        required=False,
        widget=SmartSelect(
            kind_key="product_type", allow_create=False,
            attrs={"disabled": "disabled"}
        ),
    )

    molecular_type = forms.ChoiceField(
        label="Molecular Type",
        required=True,
        choices=[("", "— Select molecular workflow —")] + list(Sample.MolecularType.choices),
        widget=forms.Select(attrs={"class": "form-input", "id": "id_molecular_type"}),
    )

    requested_test = forms.CharField(
        label="Requested Test Method",
        required=False,  # validated manually in clean()
        widget=SmartSelect(
            kind_key="lab_method", allow_create=False,
            attrs={"disabled": "disabled"}
        ),
    )

    assigned_to = SmartModelChoiceField(
        kind_key="user", allow_create=False, required=False, label="Assigned Technician"
    )

    class Meta:
        model = Sample
        fields = [
            "product_name", "priority", "storage_condition", "due_date",
            "received_date", "production_date", "expiry_date",
            "assigned_to", "remarks",
        ]
        widgets = {
            "product_name": forms.TextInput(attrs={"class": "form-input"}),
            "priority": forms.Select(attrs={"class": "form-input"}),
            "storage_condition": forms.Select(attrs={"class": "form-input"}),
            "due_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "received_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "production_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "expiry_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "remarks": forms.Textarea(attrs={"class": "form-textarea", "rows": 2}),
        }

    def __init__(self, *args, next_url="", hide_advanced=False,
                 lock_molecular_type=False, initial_molecular_type=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Set next_url on all smart widgets
        for name in ("client_name", "product_category", "product_type", "requested_test", "assigned_to"):
            if name in self.fields:
                w = self.fields[name].widget
                if hasattr(w, "next_url"):
                    w.next_url = next_url
                self.fields[name].widget.attrs.setdefault("id", f"id_{name}")

        self.fields["product_name"].required = True
        self.fields["received_date"].required = True

        # Store for use in clean()
        self._initial_molecular_type = initial_molecular_type
        self._lock_molecular_type = lock_molecular_type

        if initial_molecular_type:
            self.fields["molecular_type"].initial = initial_molecular_type
            # Unlock requested_test immediately
            self.fields["requested_test"].widget.attrs.pop("disabled", None)
            if lock_molecular_type:
                self.fields["molecular_type"].widget.attrs["disabled"] = "disabled"
                self.fields["molecular_type"].widget.attrs["style"] = (
                    "background:var(--ok-light);border-color:var(--ok);"
                )

        # On POST: unlock widgets if values were submitted
        if self.data:
            client_text = (self.data.get("client_name__text") or "").strip()
            client_pk = (self.data.get("client_name") or "").strip()
            if client_text and not client_pk:
                self.fields["client_phone"].widget.attrs.pop("disabled", None)

            cat_pk = (self.data.get("product_category") or "").strip()
            cat_text = (self.data.get("product_category__text") or "").strip()
            if cat_pk or cat_text:
                self.fields["product_type"].widget.attrs.pop("disabled", None)

            mol = (self.data.get("molecular_type") or self.data.get("molecular_type_mirror") or "").strip()
            if mol:
                self.fields["requested_test"].widget.attrs.pop("disabled", None)

        if hide_advanced:
            for f in ("production_date", "expiry_date", "assigned_to"):
                self.fields.pop(f, None)

    def _text_or_pk(self, field):
        """Return text label or raw pk value for smart select fields."""
        text = (self.data.get(f"{field}__text") or "").strip()
        raw = (self.data.get(field) or "").strip()
        return text or raw

    def clean_molecular_type(self):
        val = (self.cleaned_data.get("molecular_type") or "").strip()
        if not val and self._initial_molecular_type:
            # Locked field wasn't submitted — use the initial value
            return self._initial_molecular_type
        if not val:
            # Check mirror hidden field
            mirror = (self.data.get("molecular_type_mirror") or "").strip()
            if mirror:
                return mirror
            raise forms.ValidationError("You must select a molecular type.")
        return val

    def clean_product_name(self):
        name = (self.cleaned_data.get("product_name") or "").strip()
        if not name:
            raise forms.ValidationError("Product name is required.")
        return name

    def clean(self):
        cleaned = super().clean()

        # Safely extract smart-select text values — never crash here
        cleaned["_category_text"] = self._text_or_pk("product_category")
        cleaned["_type_text"] = self._text_or_pk("product_type")
        cleaned["_test_text"] = self._text_or_pk("requested_test")
        cleaned["_client_text"] = self._text_or_pk("client_name")

        # Molecular type fallback (disabled field not submitted by browser)
        if not cleaned.get("molecular_type"):
            mirror = (self.data.get("molecular_type_mirror") or "").strip()
            if mirror:
                cleaned["molecular_type"] = mirror
            elif self._initial_molecular_type:
                cleaned["molecular_type"] = self._initial_molecular_type

        # Validate requested test only if molecular type is set
        mol = cleaned.get("molecular_type")
        test_text = cleaned.get("_test_text", "")
        if mol and not test_text:
            self.add_error("requested_test", "A requested test method is required.")

        return cleaned


class AdvanceStatusForm(forms.Form):
    """Simple hardcoded status dropdown — no database lookup."""
    to_state = forms.ChoiceField(
        label="New Status",
        choices=Sample.WorkflowState.choices,
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-textarea", "rows": 2}),
    )