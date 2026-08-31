import logging
import secrets
import uuid
from decimal import Decimal, ROUND_HALF_UP

import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import DatabaseError, IntegrityError, transaction
from django.http import Http404
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, View

from .forms import CheckoutForm, CouponForm, PaymentForm, RefundForm
from .models import Address, Coupon, Item, Order, OrderItem, Payment, Refund


logger = logging.getLogger(__name__)
ANONYMOUS_CART_SESSION_KEY = "anonymous_cart"


def create_ref_code():
    for _ in range(10):
        candidate = secrets.token_hex(10)
        if not Order.objects.filter(ref_code=candidate).exists():
            return candidate
    raise RuntimeError("Unable to allocate a unique order reference.")


def _active_order(user, *, for_update=False):
    queryset = Order.objects.filter(user=user, ordered=False)
    if for_update:
        queryset = queryset.select_for_update()
    return queryset.prefetch_related("items__item").first()


def _anonymous_cart_data(request):
    """Return a validated copy of the anonymous session cart."""
    cart = request.session.get(ANONYMOUS_CART_SESSION_KEY, {})
    if not isinstance(cart, dict):
        return {}
    clean_cart = {}
    for slug, quantity in cart.items():
        if isinstance(slug, str) and isinstance(quantity, int) and quantity > 0:
            clean_cart[slug] = quantity
    return clean_cart


def _cart_return_url(request):
    """Return only an on-site POST destination for cart mutations."""
    candidate = request.POST.get("next", "")
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return "core:home"


def _save_anonymous_cart(request, cart):
    request.session[ANONYMOUS_CART_SESSION_KEY] = cart
    request.session.modified = True


def _anonymous_cart_context(request):
    cart = _anonymous_cart_data(request)
    items_by_slug = Item.objects.in_bulk(cart.keys(), field_name="slug")
    entries = []
    total = Decimal("0.00")
    for slug, quantity in cart.items():
        item = items_by_slug.get(slug)
        if not item:
            continue
        unit_price = item.discount_price if item.discount_price is not None else item.price
        line_total = unit_price * quantity
        total += line_total
        entries.append({"item": item, "quantity": quantity, "line_total": line_total})
    return {"anonymous_items": entries, "anonymous_total": total}


def _merge_anonymous_cart(request):
    """Move an existing session cart into the signed-in user's only active order."""
    if not request.user.is_authenticated:
        return
    cart = _anonymous_cart_data(request)
    if not cart:
        return
    items_by_slug = Item.objects.in_bulk(cart.keys(), field_name="slug")
    with transaction.atomic():
        order = _active_order(request.user, for_update=True)
        if not order:
            order = Order.objects.create(
                user=request.user,
                ordered_date=timezone.now(),
                status=Order.Status.CART,
            )
        for slug, quantity in cart.items():
            item = items_by_slug.get(slug)
            if not item:
                continue
            order_item, created = OrderItem.objects.get_or_create(
                item=item,
                user=request.user,
                ordered=False,
                defaults={"quantity": quantity},
            )
            if not created:
                order_item.quantity += quantity
                order_item.save(update_fields=("quantity",))
            if not order.items.filter(pk=order_item.pk).exists():
                order.items.add(order_item)
    request.session.pop(ANONYMOUS_CART_SESSION_KEY, None)
    request.session.modified = True


def _checkout_context(order, form=None):
    user = order.user
    return {
        "form": form or CheckoutForm(),
        "couponform": CouponForm(),
        "order": order,
        "DISPLAY_COUPON_FORM": True,
        "default_shipping_address": Address.objects.filter(
            user=user, address_type="S", default=True
        ).first(),
        "default_billing_address": Address.objects.filter(
            user=user, address_type="B", default=True
        ).first(),
    }


def _create_address(user, cleaned_data, prefix, address_type, make_default):
    if make_default:
        Address.objects.filter(user=user, address_type=address_type, default=True).update(
            default=False
        )
    return Address.objects.create(
        user=user,
        street_address=cleaned_data[f"{prefix}_address"],
        apartment_address=cleaned_data.get(f"{prefix}_address2", ""),
        country="PK",
        zip=cleaned_data[f"{prefix}_zip"],
        address_type=address_type,
        default=make_default,
    )


class CheckoutView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        _merge_anonymous_cart(request)
        order = _active_order(request.user)
        if not order:
            messages.info(request, "Your cart is empty.")
            return redirect("core:home")
        return render(request, "checkout.html", _checkout_context(order))

    def post(self, request, *args, **kwargs):
        _merge_anonymous_cart(request)
        form = CheckoutForm(request.POST)
        order = _active_order(request.user)
        if not order:
            messages.warning(request, "Your cart is empty.")
            return redirect("core:order-summary")
        if not form.is_valid():
            messages.warning(request, "Please correct the checkout form errors.")
            return render(request, "checkout.html", _checkout_context(order, form), status=400)

        data = form.cleaned_data
        default_shipping = None
        default_billing = None
        if data["use_default_shipping"]:
            default_shipping = Address.objects.filter(
                user=request.user, address_type="S", default=True
            ).first()
            if not default_shipping:
                messages.warning(request, "No default shipping address is available.")
                return redirect("core:checkout")
        if data["use_default_billing"]:
            default_billing = Address.objects.filter(
                user=request.user, address_type="B", default=True
            ).first()
            if not default_billing:
                messages.warning(request, "No default billing address is available.")
                return redirect("core:checkout")

        with transaction.atomic():
            order = get_object_or_404(
                Order.objects.select_for_update(), pk=order.pk, user=request.user, ordered=False
            )

            if data["use_default_shipping"]:
                shipping_address = default_shipping
            else:
                shipping_address = _create_address(
                    request.user,
                    data,
                    "shipping",
                    "S",
                    data["set_default_shipping"],
                )

            if data["same_billing_address"]:
                if data["set_default_billing"]:
                    Address.objects.filter(
                        user=request.user, address_type="B", default=True
                    ).update(default=False)
                billing_address = Address.objects.create(
                    user=request.user,
                    street_address=shipping_address.street_address,
                    apartment_address=shipping_address.apartment_address,
                    country="PK",
                    zip=shipping_address.zip,
                    address_type="B",
                    default=data["set_default_billing"],
                )
            elif data["use_default_billing"]:
                billing_address = default_billing
            else:
                billing_address = _create_address(
                    request.user,
                    data,
                    "billing",
                    "B",
                    data["set_default_billing"],
                )

            order.shipping_address = shipping_address
            order.billing_address = billing_address
            order.save(update_fields=("shipping_address", "billing_address"))

        return redirect("core:payment", payment_option="stripe")


class PaymentView(LoginRequiredMixin, View):
    def _get_order(self, request):
        order = _active_order(request.user)
        if not order:
            messages.warning(request, "Your cart is empty.")
            return None
        if not order.billing_address_id or order.billing_address.user_id != request.user.id:
            messages.warning(request, "Add a billing address before payment.")
            return None
        return order

    def get(self, request, payment_option, *args, **kwargs):
        if payment_option != "stripe":
            raise Http404("Payment option not found.")
        order = self._get_order(request)
        if not order:
            return redirect("core:checkout")
        if not settings.STRIPE_PUBLIC_KEY:
            messages.warning(request, "Stripe test mode is not configured.")
            return redirect("core:checkout")

        session_key = f"payment_idempotency_key_{order.pk}"
        idempotency_key = request.session.get(session_key)
        if not idempotency_key:
            idempotency_key = str(uuid.uuid4())
            request.session[session_key] = idempotency_key
        context = {
            "order": order,
            "DISPLAY_COUPON_FORM": False,
            "STRIPE_PUBLIC_KEY": settings.STRIPE_PUBLIC_KEY,
            "idempotency_key": idempotency_key,
        }
        return render(request, "payment.html", context)

    def post(self, request, payment_option, *args, **kwargs):
        if payment_option != "stripe":
            raise Http404("Payment option not found.")
        form = PaymentForm(request.POST)
        if not form.is_valid():
            messages.warning(request, "Invalid payment data.")
            return redirect("core:payment", payment_option="stripe")

        idempotency_key = form.cleaned_data["idempotency_key"]
        existing_payment = Payment.objects.filter(idempotency_key=idempotency_key).first()
        if existing_payment and existing_payment.user_id != request.user.id:
            messages.warning(request, "Invalid payment request.")
            return redirect("core:order-summary")
        if existing_payment and existing_payment.status == Payment.Status.SUCCEEDED:
            completed_order = Order.objects.filter(
                user=request.user, payment=existing_payment, ordered=True
            ).first()
            if completed_order:
                return redirect("core:order-detail", ref_code=completed_order.ref_code)

        order = self._get_order(request)
        if not order:
            return redirect("core:order-summary")
        expected_key = request.session.get(f"payment_idempotency_key_{order.pk}")
        if expected_key != str(idempotency_key):
            messages.warning(request, "The payment form expired. Please try again.")
            return redirect("core:payment", payment_option="stripe")
        if not settings.STRIPE_SECRET_KEY:
            messages.warning(request, "Stripe test mode is not configured.")
            return redirect("core:payment", payment_option="stripe")

        amount = order.get_total()
        if amount <= Decimal("0.00"):
            messages.warning(request, "The order total must be greater than zero.")
            return redirect("core:order-summary")

        try:
            with transaction.atomic():
                locked_order = get_object_or_404(
                    Order.objects.select_for_update(),
                    pk=order.pk,
                    user=request.user,
                    ordered=False,
                )
                payment, _ = Payment.objects.get_or_create(
                    idempotency_key=idempotency_key,
                    defaults={
                        "user": request.user,
                        "amount": amount,
                        "currency": "PKR",
                        "status": Payment.Status.PENDING,
                    },
                )
                if payment.user_id != request.user.id or payment.amount != amount:
                    messages.warning(request, "The order changed. Restart payment.")
                    return redirect("core:order-summary")
                payment.status = Payment.Status.PENDING
                payment.error_code = ""
                payment.save(update_fields=("status", "error_code", "updated_at"))
                locked_order.status = Order.Status.PAYMENT_PENDING
                locked_order.save(update_fields=("status",))
        except IntegrityError:
            messages.info(request, "This payment is already being processed.")
            return redirect("core:payment", payment_option="stripe")

        amount_minor = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            intent = stripe.PaymentIntent.create(
                amount=amount_minor,
                currency="pkr",
                payment_method=form.cleaned_data["stripe_payment_method_id"],
                confirm=True,
                error_on_requires_action=True,
                description=f"Ecom Website order {order.pk}",
                metadata={"order_id": str(order.pk), "user_id": str(request.user.pk)},
                idempotency_key=str(idempotency_key),
            )
        except stripe.CardError:
            self._mark_failed(payment, order, "card_declined", request=request, rotate_key=True)
            messages.warning(request, "The test payment was declined.")
            return redirect("core:payment", payment_option="stripe")
        except stripe.APIConnectionError:
            self._mark_failed(payment, order, "provider_timeout")
            messages.warning(request, "The payment provider could not be reached. Please retry.")
            return redirect("core:payment", payment_option="stripe")
        except stripe.StripeError:
            self._mark_failed(payment, order, "provider_error")
            messages.warning(request, "The payment could not be completed.")
            return redirect("core:payment", payment_option="stripe")

        intent_id = getattr(intent, "id", None) or intent.get("id")
        intent_status = getattr(intent, "status", None) or intent.get("status")
        if intent_status != "succeeded" or not intent_id:
            self._mark_failed(payment, order, "provider_incomplete")
            messages.warning(request, "The payment was not completed.")
            return redirect("core:payment", payment_option="stripe")

        try:
            with transaction.atomic():
                locked_order = Order.objects.select_for_update().get(
                    pk=order.pk, user=request.user, ordered=False
                )
                locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
                if locked_order.get_total() != locked_payment.amount:
                    raise IntegrityError("Order total changed during payment.")
                locked_payment.provider_payment_id = intent_id
                locked_payment.status = Payment.Status.SUCCEEDED
                locked_payment.error_code = ""
                locked_payment.save(
                    update_fields=("provider_payment_id", "status", "error_code", "updated_at")
                )
                locked_order.items.update(ordered=True)
                locked_order.ordered = True
                locked_order.status = Order.Status.PAID
                locked_order.payment = locked_payment
                locked_order.ref_code = create_ref_code()
                locked_order.ordered_date = timezone.now()
                locked_order.save(
                    update_fields=(
                        "ordered",
                        "status",
                        "payment",
                        "ref_code",
                        "ordered_date",
                    )
                )
        except (DatabaseError, Order.DoesNotExist):
            Payment.objects.filter(pk=payment.pk).update(
                status=Payment.Status.RECONCILIATION_REQUIRED,
                error_code="local_finalize_failed",
            )
            logger.error(
                "Local payment finalization failed; reconciliation required.",
                extra={"payment_id": payment.pk, "order_id": order.pk},
            )
            messages.error(request, "Payment needs manual reconciliation. Contact support.")
            return redirect("core:order-summary")

        request.session.pop(f"payment_idempotency_key_{order.pk}", None)
        messages.success(request, "Your test-mode payment succeeded.")
        return redirect("core:order-detail", ref_code=locked_order.ref_code)

    @staticmethod
    def _mark_failed(payment, order, code, *, request=None, rotate_key=False):
        Payment.objects.filter(pk=payment.pk).update(status=Payment.Status.FAILED, error_code=code)
        Order.objects.filter(pk=order.pk, ordered=False).update(status=Order.Status.CART)
        logger.warning(
            "Payment attempt failed.",
            extra={"payment_id": payment.pk, "order_id": order.pk, "error_code": code},
        )
        if rotate_key and request is not None:
            request.session[f"payment_idempotency_key_{order.pk}"] = str(uuid.uuid4())


class HomeView(ListView):
    model = Item
    paginate_by = 10
    template_name = "home.html"

    def get_queryset(self):
        """Filter the existing catalog for the header search field."""
        queryset = Item.objects.all()
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) | Q(description__icontains=query)
            )
        return queryset.order_by("title")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "").strip()
        return context


class OrderSummaryView(View):
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return render(request, "order_summary.html", _anonymous_cart_context(request))
        _merge_anonymous_cart(request)
        order = _active_order(request.user)
        if not order:
            messages.info(request, "Your cart is empty.")
            return redirect("core:home")
        return render(request, "order_summary.html", {"object": order})


class OrderDetailView(LoginRequiredMixin, DetailView):
    model = Order
    template_name = "order_detail.html"
    context_object_name = "order"
    slug_field = "ref_code"
    slug_url_kwarg = "ref_code"

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user, ordered=True).prefetch_related(
            "items__item"
        )


class ItemDetailView(DetailView):
    model = Item
    template_name = "product.html"


@require_POST
def add_to_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    if not request.user.is_authenticated:
        cart = _anonymous_cart_data(request)
        cart[item.slug] = cart.get(item.slug, 0) + 1
        _save_anonymous_cart(request, cart)
        messages.info(request, "Item added to your cart.")
        return redirect(_cart_return_url(request))
    with transaction.atomic():
        order = _active_order(request.user, for_update=True)
        if not order:
            order = Order.objects.create(
                user=request.user,
                ordered_date=timezone.now(),
                status=Order.Status.CART,
            )
        order_item, created = OrderItem.objects.get_or_create(
            item=item,
            user=request.user,
            ordered=False,
            defaults={"quantity": 1},
        )
        if not created and order.items.filter(pk=order_item.pk).exists():
            order_item.quantity += 1
            order_item.save(update_fields=("quantity",))
            message = "Item quantity updated."
        else:
            order.items.add(order_item)
            message = "Item added to your cart."
    messages.info(request, message)
    return redirect(_cart_return_url(request))


@require_POST
def remove_from_cart(request, slug):
    if not request.user.is_authenticated:
        cart = _anonymous_cart_data(request)
        if slug not in cart:
            messages.info(request, "That item is not in your cart.")
        else:
            cart.pop(slug)
            _save_anonymous_cart(request, cart)
            messages.info(request, "Item removed from your cart.")
        return redirect("core:order-summary")
    with transaction.atomic():
        order = _active_order(request.user, for_update=True)
        if not order:
            messages.info(request, "Your cart is empty.")
            return redirect("core:home")
        order_item = order.items.filter(item__slug=slug, user=request.user, ordered=False).first()
        if not order_item:
            messages.info(request, "That item is not in your cart.")
            return redirect("core:order-summary")
        order.items.remove(order_item)
        order_item.delete()
    messages.info(request, "Item removed from your cart.")
    return redirect("core:order-summary")


@require_POST
def remove_single_item_from_cart(request, slug):
    if not request.user.is_authenticated:
        cart = _anonymous_cart_data(request)
        if slug not in cart:
            messages.info(request, "That item is not in your cart.")
        elif cart[slug] > 1:
            cart[slug] -= 1
            _save_anonymous_cart(request, cart)
            messages.info(request, "Item quantity updated.")
        else:
            cart.pop(slug)
            _save_anonymous_cart(request, cart)
            messages.info(request, "Item removed from your cart.")
        return redirect("core:order-summary")
    with transaction.atomic():
        order = _active_order(request.user, for_update=True)
        if not order:
            messages.info(request, "Your cart is empty.")
            return redirect("core:home")
        order_item = order.items.filter(item__slug=slug, user=request.user, ordered=False).first()
        if not order_item:
            messages.info(request, "That item is not in your cart.")
            return redirect("core:order-summary")
        if order_item.quantity > 1:
            order_item.quantity -= 1
            order_item.save(update_fields=("quantity",))
        else:
            order.items.remove(order_item)
            order_item.delete()
    messages.info(request, "Item quantity updated.")
    return redirect("core:order-summary")


def get_coupon(code):
    now = timezone.now()
    return Coupon.objects.filter(active=True, code=code).filter(
        (Q(valid_from__isnull=True) | Q(valid_from__lte=now)),
        (Q(valid_until__isnull=True) | Q(valid_until__gt=now)),
    ).first()


class AddCouponView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = CouponForm(request.POST)
        if not form.is_valid():
            messages.info(request, "Enter a valid coupon code.")
            return redirect("core:checkout")
        order = _active_order(request.user)
        if not order:
            messages.info(request, "Your cart is empty.")
            return redirect("core:home")
        coupon = get_coupon(form.cleaned_data["code"])
        if not coupon:
            messages.info(request, "That coupon is invalid or expired.")
            return redirect("core:checkout")
        order.coupon = coupon
        order.save(update_fields=("coupon",))
        messages.success(request, "Coupon applied.")
        return redirect("core:checkout")


class RequestRefundView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        return render(request, "request_refund.html", {"form": RefundForm()})

    def post(self, request, *args, **kwargs):
        form = RefundForm(request.POST)
        if not form.is_valid():
            return render(request, "request_refund.html", {"form": form}, status=400)
        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(
                    ref_code=form.cleaned_data["ref_code"],
                    user=request.user,
                    ordered=True,
                    status__in=(Order.Status.PAID, Order.Status.FULFILLED),
                )
                if order.refund_requested:
                    messages.info(request, "A refund has already been requested for this order.")
                    return redirect("core:request-refund")
                order.refund_requested = True
                order.status = Order.Status.REFUND_REQUESTED
                order.save(update_fields=("refund_requested", "status"))
                Refund.objects.create(
                    order=order,
                    reason=form.cleaned_data["message"],
                    email=form.cleaned_data["email"],
                )
        except Order.DoesNotExist:
            messages.info(request, "No matching order was found for your account.")
            return redirect("core:request-refund")
        messages.info(request, "Your refund request was received.")
        return redirect("core:order-detail", ref_code=order.ref_code)
