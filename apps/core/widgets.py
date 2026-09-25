"""
SmartSelect widget & SmartModelChoiceField — text input with server-driven type-ahead.
No <select> dropdowns. Accepts both UUID selection and text resolution.
"""
import uuid
from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.core.smart_select import SmartRegistry, smart_resolve, smart_search


class SmartModelChoiceField(forms.ModelChoiceField):
    """Custom ChoiceField that accepts both UUID primary keys AND typed text strings."""

    def __init__(self, kind_key, allow_create=False, next_url="", *args, **kwargs):
        self.kind_key = kind_key
        kind = SmartRegistry.get(kind_key)
        if kind and "queryset" not in kwargs:
            kwargs["queryset"] = kind.queryset_fn()

        widget = SmartSelect(kind_key=kind_key, allow_create=allow_create, next_url=next_url)
        kwargs["widget"] = widget
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if not value:
            return None
        if isinstance(value, self.queryset.model):
            return value

        val_str = str(value).strip()
        if not val_str:
            return None

        # 1. Try as UUID
        try:
            uuid.UUID(val_str)
            obj = super().to_python(val_str)
            if obj:
                return obj
        except (ValueError, TypeError, ValidationError, AttributeError):
            pass

        # 2. Try text resolution
        kind = SmartRegistry.get(self.kind_key)
        if kind:
            status, pk, message, _ = smart_resolve(kind, val_str)
            if status == "resolved":
                return kind.queryset_fn().filter(pk=pk).first()
            elif status == "ambiguous":
                raise forms.ValidationError(message)
            elif status == "not_found":
                raise forms.ValidationError(
                    f"'{val_str}' was not found. Please choose from the list or add it."
                )

        raise forms.ValidationError(f"Invalid selection: '{val_str}'")


class SmartSelect(forms.Widget):
    template_name = "widgets/smart_select.html"

    def __init__(self, kind_key, attrs=None, allow_create=False, next_url=""):
        super().__init__(attrs)
        self.kind_key = kind_key
        self.allow_create = allow_create
        self.next_url = next_url

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        kind = SmartRegistry.get(self.kind_key)
        if kind is None:
            raise ValueError(f"SmartSelect kind '{self.kind_key}' is not registered.")

        datalist_items = list(smart_search(kind, "", limit=25))

        selected_display = ""
        selected_code = ""
        if value:
            if isinstance(value, kind.queryset_fn().model):
                selected_display = kind.display_fn(value)
                selected_code = kind.code_fn(value)
                value = kind.value_fn(value)
            else:
                val_str = str(value)
                is_uuid = False
                try:
                    uuid.UUID(val_str)
                    is_uuid = True
                except (ValueError, TypeError, AttributeError):
                    is_uuid = False

                if is_uuid:
                    try:
                        obj = kind.queryset_fn().filter(pk=val_str).first()
                        if obj:
                            selected_display = kind.display_fn(obj)
                            selected_code = kind.code_fn(obj)
                    except Exception:
                        selected_display = val_str
                else:
                    selected_display = val_str

        try:
            results_url = reverse("core:smart_select_results", args=[self.kind_key])
        except Exception:
            results_url = f"/smart/results/{self.kind_key}/"

        try:
            picker_url = reverse("core:smart_picker", args=[self.kind_key])
        except Exception:
            picker_url = f"/smart/pick/{self.kind_key}/"

        create_url = ""
        if self.allow_create and kind.create_url_name:
            try:
                create_url = reverse(kind.create_url_name)
            except Exception:
                create_url = ""

        final_attrs = context["widget"]["attrs"]
        input_id = final_attrs.get("id") or f"id_{name}"

        context["widget"].update({
            "kind_key": self.kind_key,
            "kind_label": kind.label,
            "datalist_items": [
                {
                    "value": kind.display_fn(o),
                    "code": kind.code_fn(o),
                    "sub": kind.sub_fn(o),
                    "pk": kind.value_fn(o),
                }
                for o in datalist_items
            ],
            "results_url": results_url,
            "picker_url": picker_url,
            "create_url": create_url,
            "allow_create": bool(self.allow_create and create_url),
            "selected_display": selected_display,
            "selected_code": selected_code,
            "next_url": self.next_url or "",
            "input_id": input_id,
            "name": name,
            "value": value or "",
        })
        return context

    def format_value(self, value):
        if value is None:
            return ""
        return str(value)

    def value_from_datadict(self, data, files, name):
        pk_value = data.get(name, "").strip()
        text_value = data.get(f"{name}__text", "").strip()
        return pk_value or text_value

    class Media:
        css = {"all": ("css/smart_select.css",)}


class SmartResolveMixin:
    """Form mixin for compatibility with non-SmartModelChoiceField forms."""
    smart_fields: dict = {}