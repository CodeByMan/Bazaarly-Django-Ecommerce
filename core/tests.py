import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import stripe
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import DatabaseError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Address, Coupon, Item, Order, OrderItem, Payment, Refund


User = get_user_model()


class CommerceTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="owner", email="owner@example.com", password="strong-test-password"
        )
        self.other_user = User.objects.create_user(
            username="other", email="other@example.com", password="strong-test-password"
        )
        self.item = Item.objects.create(
            title="Karachi Test Shirt",
            price=Decimal("0.10"),
            discount_price=None,
            category="S",
            label="P",
            slug="karachi-test-shirt",
            description="Synthetic test catalog item.",
        )

    def make_address(self, user, address_type):
        return Address.objects.create(
            user=user,
            street_address="12 Demo Lane, Karachi",
            apartment_address="",
            country="PK",
            zip="75600",
            address_type=address_type,
            default=True,
        )

    def make_cart(self, user=None, quantity=1, with_addresses=False):
        user = user or self.user
        order_item = OrderItem.objects.create(user=user, item=self.item, quantity=quantity)
        order = Order.objects.create(user=user, ordered_date=timezone.now())
        order.items.add(order_item)
        if with_addresses:
            order.shipping_address = self.make_address(user, "S")
            order.billing_address = self.make_address(user, "B")
            order.save(update_fields=("shipping_address", "billing_address"))
        return order

    def make_completed_order(self, user=None, ref_code="completed-order-01"):
        user = user or self.user
        order_item = OrderItem.objects.create(
            user=user, item=self.item, quantity=1, ordered=True
        )
        order = Order.objects.create(
            user=user,
            ordered_date=timezone.now(),
            ordered=True,
            status=Order.Status.PAID,
            ref_code=ref_code,
        )
        order.items.add(order_item)
        return order


class AuthorizationAndHttpSafetyTests(CommerceTestCase):
    def test_anonymous_checkout_payment_and_refund_are_denied(self):
        self.make_cart(with_addresses=True)
        protected_urls = [
            reverse("core:checkout"),
            reverse("core:payment", kwargs={"payment_option": "stripe"}),
            reverse("core:request-refund"),
        ]
        for url in protected_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login/", response.url)

    def test_user_cannot_view_another_users_order(self):
        order = self.make_completed_order(self.other_user, "other-order-000001")
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("core:order-detail", kwargs={"ref_code": order.ref_code})
        )
        self.assertEqual(response.status_code, 404)

    def test_user_cannot_refund_another_users_order(self):
        order = self.make_completed_order(self.other_user, "other-order-000002")
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("core:request-refund"),
            {"ref_code": order.ref_code, "message": "Not mine", "email": "owner@example.com"},
        )
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertFalse(order.refund_requested)
        self.assertFalse(Refund.objects.filter(order=order).exists())

    def test_owner_can_request_refund_once(self):
        order = self.make_completed_order(self.user, "owner-order-000001")
        self.client.force_login(self.user)
        data = {
            "ref_code": order.ref_code,
            "message": "Synthetic refund reason",
            "email": "owner@example.com",
        }
        self.client.post(reverse("core:request-refund"), data)
        self.client.post(reverse("core:request-refund"), data)
        order.refresh_from_db()
        self.assertTrue(order.refund_requested)
        self.assertEqual(order.status, Order.Status.REFUND_REQUESTED)
        self.assertEqual(Refund.objects.filter(order=order).count(), 1)

    def test_get_cart_mutations_return_405(self):
        self.make_cart()
        self.client.force_login(self.user)
        for name in ("add-to-cart", "remove-from-cart", "remove-single-item-from-cart"):
            with self.subTest(name=name):
                response = self.client.get(reverse(f"core:{name}", kwargs={"slug": self.item.slug}))
                self.assertEqual(response.status_code, 405)

    def test_post_mutation_requires_csrf_and_only_changes_current_users_cart(self):
        other_order = self.make_cart(self.other_user)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        url = reverse("core:add-to-cart", kwargs={"slug": self.item.slug})
        self.assertEqual(csrf_client.post(url).status_code, 403)

        response = csrf_client.get(reverse("core:product", kwargs={"slug": self.item.slug}))
        self.assertEqual(response.status_code, 200)
        token = csrf_client.cookies["csrftoken"].value
        self.assertEqual(
            csrf_client.post(url, HTTP_X_CSRFTOKEN=token).status_code,
            302,
        )
        self.assertEqual(Order.objects.filter(user=self.user, ordered=False).count(), 1)
        other_order.refresh_from_db()
        self.assertEqual(other_order.items.get().quantity, 1)


class CouponAndMoneyTests(CommerceTestCase):
    def setUp(self):
        super().setUp()
        self.order = self.make_cart(quantity=3, with_addresses=True)
        self.client.force_login(self.user)

    def test_decimal_totals_are_exact(self):
        coupon = Coupon.objects.create(code="EXACT10", amount=Decimal("0.10"))
        self.order.coupon = coupon
        self.order.save(update_fields=("coupon",))
        self.assertEqual(self.order.get_total(), Decimal("0.20"))

    def test_coupon_valid_invalid_and_expired_behavior(self):
        valid = Coupon.objects.create(code="VALID10", amount=Decimal("0.10"))
        Coupon.objects.create(
            code="EXPIRED10",
            amount=Decimal("0.10"),
            valid_until=timezone.now() - timedelta(seconds=1),
        )

        self.client.post(reverse("core:add-coupon"), {"code": "valid10"})
        self.order.refresh_from_db()
        self.assertEqual(self.order.coupon, valid)

        self.order.coupon = None
        self.order.save(update_fields=("coupon",))
        for code in ("MISSING", "EXPIRED10"):
            with self.subTest(code=code):
                self.client.post(reverse("core:add-coupon"), {"code": code})
                self.order.refresh_from_db()
                self.assertIsNone(self.order.coupon)

    def test_checkout_ui_contains_no_paypal(self):
        response = self.client.get(reverse("core:checkout"))
        self.assertNotContains(response, "PayPal", status_code=200)

    def test_catalog_search_filters_existing_items(self):
        response = self.client.get(reverse("core:home"), {"q": "Karachi Test"})
        self.assertContains(response, "Karachi Test Shirt", status_code=200)
        self.assertContains(response, "Search results for", status_code=200)


@override_settings(
    STRIPE_PUBLIC_KEY="pk_test_unit_test_placeholder",
    STRIPE_SECRET_KEY="sk_test_unit_test_placeholder",
)
class PaymentTests(CommerceTestCase):
    def setUp(self):
        super().setUp()
        self.order = self.make_cart(quantity=2, with_addresses=True)
        self.client.force_login(self.user)
        self.payment_url = reverse("core:payment", kwargs={"payment_option": "stripe"})

    def payment_form_data(self):
        self.client.get(self.payment_url)
        key = self.client.session[f"payment_idempotency_key_{self.order.pk}"]
        return {"stripe_payment_method_id": "pm_card_unit_test", "idempotency_key": key}

    @patch("core.views.stripe.PaymentIntent.create")
    def test_stripe_success_is_mocked_and_finalized(self, create_intent):
        create_intent.return_value = SimpleNamespace(id="pi_unit_test_success", status="succeeded")
        response = self.client.post(self.payment_url, self.payment_form_data())
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertTrue(self.order.ordered)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.order.payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(self.order.payment.amount, Decimal("0.20"))
        self.assertEqual(self.order.payment.currency, "PKR")
        self.assertEqual(create_intent.call_args.kwargs["currency"], "pkr")
        self.assertEqual(create_intent.call_args.kwargs["amount"], 20)

    @patch("core.views.stripe.PaymentIntent.create")
    def test_duplicate_submission_calls_provider_once(self, create_intent):
        create_intent.return_value = SimpleNamespace(id="pi_unit_test_duplicate", status="succeeded")
        data = self.payment_form_data()
        self.client.post(self.payment_url, data)
        second = self.client.post(self.payment_url, data)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(create_intent.call_count, 1)
        self.assertEqual(Payment.objects.count(), 1)

    @patch("core.views.stripe.PaymentIntent.create")
    def test_decline_is_mocked_and_marks_payment_failed(self, create_intent):
        create_intent.side_effect = stripe.CardError(
            message="Synthetic decline", param=None, code="card_declined"
        )
        self.client.post(self.payment_url, self.payment_form_data())
        payment = Payment.objects.get()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertEqual(payment.error_code, "card_declined")
        self.order.refresh_from_db()
        self.assertFalse(self.order.ordered)

    @patch("core.views.stripe.PaymentIntent.create")
    def test_timeout_is_mocked_and_marks_payment_failed(self, create_intent):
        create_intent.side_effect = stripe.APIConnectionError("Synthetic timeout")
        self.client.post(self.payment_url, self.payment_form_data())
        payment = Payment.objects.get()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertEqual(payment.error_code, "provider_timeout")

    @patch("core.views.stripe.PaymentIntent.create")
    def test_local_finalize_failure_rolls_back_and_requires_reconciliation(self, create_intent):
        create_intent.return_value = SimpleNamespace(id="pi_unit_test_reconcile", status="succeeded")
        data = self.payment_form_data()
        original_save = Order.save

        def fail_paid_save(instance, *args, **kwargs):
            if instance.status == Order.Status.PAID:
                raise DatabaseError("Synthetic local database failure")
            return original_save(instance, *args, **kwargs)

        with patch.object(Order, "save", new=fail_paid_save):
            response = self.client.post(self.payment_url, data)
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertFalse(self.order.ordered)
        payment = Payment.objects.get()
        self.assertEqual(payment.status, Payment.Status.RECONCILIATION_REQUIRED)
        self.assertEqual(payment.error_code, "local_finalize_failed")


class ReproducibilityAndSettingsTests(TestCase):
    def test_clean_fixture_loads_karachi_catalog(self):
        call_command("loaddata", "core/fixtures/karachi_demo.json", verbosity=0)
        self.assertEqual(Item.objects.count(), 3)
        self.assertTrue(Address.objects.filter(country="PK", street_address__icontains="Karachi").exists())
        self.assertTrue(Coupon.objects.filter(code="KARACHI500").exists())
        self.assertTrue(User.objects.filter(username="karachi.demo", password="!").exists())

    def test_production_settings_reject_missing_secrets_and_disable_debug(self):
        root = Path(__file__).resolve().parents[1]
        clean_env = {"PYTHONPATH": str(root)}
        missing = subprocess.run(
            [sys.executable, "-c", "import djecommerce.settings.production"],
            cwd=root,
            env=clean_env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(missing.returncode, 0)

        configured_env = {
            **clean_env,
            "SECRET_KEY": "x" * 60,
            "ALLOWED_HOSTS": "shop.example.com",
            "CSRF_TRUSTED_ORIGINS": "https://shop.example.com",
            "DB_NAME": "demo",
            "DB_USER": "demo",
            "DB_PASSWORD": "synthetic-password",
            "DB_HOST": "127.0.0.1",
            "STRIPE_TEST_PUBLIC_KEY": "pk_test_placeholder",
            "STRIPE_TEST_SECRET_KEY": "sk_test_placeholder",
        }
        configured = subprocess.run(
            [
                sys.executable,
                "-c",
                "from djecommerce.settings.production import DEBUG; print(DEBUG)",
            ],
            cwd=root,
            env=configured_env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(configured.returncode, 0, configured.stderr)
        self.assertEqual(configured.stdout.strip(), "False")
