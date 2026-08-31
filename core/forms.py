from django import forms

from .models import PAKISTAN_COUNTRY_CHOICES


PAYMENT_CHOICES = (("S", "Stripe test mode"),)


class CheckoutForm(forms.Form):
    shipping_address = forms.CharField(required=False, max_length=100)
    shipping_address2 = forms.CharField(required=False, max_length=100)
    shipping_country = forms.ChoiceField(
        required=False,
        choices=(("", "Select country"),) + PAKISTAN_COUNTRY_CHOICES,
        widget=forms.Select(attrs={"class": "custom-select d-block w-100"}),
    )
    shipping_zip = forms.RegexField(regex=r"^\d{5}$", required=False, max_length=5)

    billing_address = forms.CharField(required=False, max_length=100)
    billing_address2 = forms.CharField(required=False, max_length=100)
    billing_country = forms.ChoiceField(
        required=False,
        choices=(("", "Select country"),) + PAKISTAN_COUNTRY_CHOICES,
        widget=forms.Select(attrs={"class": "custom-select d-block w-100"}),
    )
    billing_zip = forms.RegexField(regex=r"^\d{5}$", required=False, max_length=5)

    same_billing_address = forms.BooleanField(required=False)
    set_default_shipping = forms.BooleanField(required=False)
    use_default_shipping = forms.BooleanField(required=False)
    set_default_billing = forms.BooleanField(required=False)
    use_default_billing = forms.BooleanField(required=False)

    payment_option = forms.ChoiceField(widget=forms.RadioSelect, choices=PAYMENT_CHOICES)

    def clean(self):
        cleaned = super().clean()
        use_default_shipping = cleaned.get("use_default_shipping")
        use_default_billing = cleaned.get("use_default_billing")
        same_billing = cleaned.get("same_billing_address")

        if use_default_shipping and cleaned.get("set_default_shipping"):
            self.add_error("set_default_shipping", "A saved address is already the default.")
        if use_default_billing and cleaned.get("set_default_billing"):
            self.add_error("set_default_billing", "A saved address is already the default.")
        if same_billing and use_default_billing:
            self.add_error(
                "use_default_billing",
                "Choose either the shipping address or the saved billing address, not both.",
            )

        if not use_default_shipping:
            self._require_address(cleaned, "shipping")
        if not same_billing and not use_default_billing:
            self._require_address(cleaned, "billing")
        return cleaned

    def _require_address(self, cleaned, prefix):
        labels = {
            "address": "Address is required.",
            "country": "Pakistan must be selected.",
            "zip": "A five-digit Pakistan postal code is required.",
        }
        for suffix, message in labels.items():
            field_name = f"{prefix}_{suffix}"
            if not cleaned.get(field_name):
                self.add_error(field_name, message)


class CouponForm(forms.Form):
    code = forms.CharField(
        max_length=15,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Promo code",
                "aria-label": "Promo code",
                "aria-describedby": "coupon-submit",
            }
        ),
    )

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()


class RefundForm(forms.Form):
    ref_code = forms.CharField(max_length=20)
    message = forms.CharField(max_length=2000, widget=forms.Textarea(attrs={"rows": 4}))
    email = forms.EmailField()

    def clean_ref_code(self):
        return self.cleaned_data["ref_code"].strip().lower()


class PaymentForm(forms.Form):
    stripe_payment_method_id = forms.RegexField(regex=r"^pm_[A-Za-z0-9_]+$", max_length=100)
    idempotency_key = forms.UUIDField()
