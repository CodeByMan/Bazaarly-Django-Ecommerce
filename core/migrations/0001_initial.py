import decimal
import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Address",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("street_address", models.CharField(max_length=100)),
                ("apartment_address", models.CharField(blank=True, max_length=100)),
                ("country", models.CharField(choices=[("PK", "Pakistan")], default="PK", max_length=2)),
                ("zip", models.CharField(max_length=5, validators=[django.core.validators.RegexValidator(message="Enter a valid five-digit Pakistan postal code.", regex="^\\d{5}$")])),
                ("address_type", models.CharField(choices=[("B", "Billing"), ("S", "Shipping")], max_length=1)),
                ("default", models.BooleanField(default=False)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name_plural": "Addresses"},
        ),
        migrations.CreateModel(
            name="Coupon",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=15, unique=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.00"))])),
                ("active", models.BooleanField(default=True)),
                ("valid_from", models.DateTimeField(blank=True, null=True)),
                ("valid_until", models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name="Item",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=100)),
                ("price", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.00"))])),
                ("discount_price", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.00"))])),
                ("category", models.CharField(choices=[("S", "Shirt"), ("SW", "Sportswear"), ("OW", "Outerwear")], max_length=2)),
                ("label", models.CharField(choices=[("P", "primary"), ("S", "secondary"), ("D", "danger")], max_length=1)),
                ("slug", models.SlugField(unique=True)),
                ("description", models.TextField()),
                ("image", models.ImageField(blank=True, upload_to="products/")),
            ],
        ),
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider_payment_id", models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ("idempotency_key", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.00"))])),
                ("currency", models.CharField(default="PKR", max_length=3)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("reconciliation_required", "Reconciliation required")], default="pending", max_length=32)),
                ("error_code", models.CharField(blank=True, max_length=64)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ordered", models.BooleanField(default=False)),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.item")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stripe_customer_id", models.CharField(blank=True, max_length=80, null=True)),
                ("one_click_purchasing", models.BooleanField(default=False)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ref_code", models.CharField(blank=True, max_length=20, null=True, unique=True)),
                ("start_date", models.DateTimeField(auto_now_add=True)),
                ("ordered_date", models.DateTimeField()),
                ("ordered", models.BooleanField(default=False)),
                ("status", models.CharField(choices=[("cart", "Cart"), ("payment_pending", "Payment pending"), ("paid", "Paid"), ("fulfilled", "Fulfilled"), ("refund_requested", "Refund requested"), ("refunded", "Refunded"), ("cancelled", "Cancelled")], default="cart", max_length=24)),
                ("being_delivered", models.BooleanField(default=False)),
                ("received", models.BooleanField(default=False)),
                ("refund_requested", models.BooleanField(default=False)),
                ("refund_granted", models.BooleanField(default=False)),
                ("billing_address", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="billing_orders", to="core.address")),
                ("coupon", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.coupon")),
                ("items", models.ManyToManyField(to="core.orderitem")),
                ("payment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.payment")),
                ("shipping_address", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="shipping_orders", to="core.address")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="Refund",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.TextField()),
                ("accepted", models.BooleanField(default=False)),
                ("email", models.EmailField(max_length=254)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.order")),
            ],
        ),
        migrations.AddConstraint(model_name="item", constraint=models.CheckConstraint(condition=models.Q(("discount_price__isnull", True)) | models.Q(("discount_price__lte", models.F("price"))), name="item_discount_not_above_price")),
        migrations.AddConstraint(model_name="orderitem", constraint=models.CheckConstraint(condition=models.Q(("quantity__gte", 1)), name="order_item_quantity_gte_1")),
        migrations.AddConstraint(model_name="orderitem", constraint=models.UniqueConstraint(condition=models.Q(("ordered", False)), fields=("user", "item"), name="unique_active_user_item")),
        migrations.AddConstraint(model_name="payment", constraint=models.CheckConstraint(condition=models.Q(("amount__gte", 0)), name="payment_amount_non_negative")),
        migrations.AddConstraint(model_name="coupon", constraint=models.CheckConstraint(condition=models.Q(("amount__gte", 0)), name="coupon_amount_non_negative")),
        migrations.AddConstraint(model_name="coupon", constraint=models.CheckConstraint(condition=models.Q(("valid_from__isnull", True)) | models.Q(("valid_until__isnull", True)) | models.Q(("valid_until__gt", models.F("valid_from"))), name="coupon_valid_window")),
        migrations.AddConstraint(model_name="order", constraint=models.UniqueConstraint(condition=models.Q(("ordered", False)), fields=("user",), name="one_active_cart_per_user")),
    ]
