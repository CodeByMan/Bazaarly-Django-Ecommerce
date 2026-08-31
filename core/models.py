import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import reverse


CATEGORY_CHOICES = (
    ("S", "Shirt"),
    ("SW", "Sportswear"),
    ("OW", "Outerwear"),
)

LABEL_CHOICES = (
    ("P", "primary"),
    ("S", "secondary"),
    ("D", "danger"),
)

ADDRESS_CHOICES = (
    ("B", "Billing"),
    ("S", "Shipping"),
)

PAKISTAN_COUNTRY_CHOICES = (("PK", "Pakistan"),)
PAKISTAN_POSTAL_CODE = RegexValidator(
    regex=r"^\d{5}$",
    message="Enter a valid five-digit Pakistan postal code.",
)


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    stripe_customer_id = models.CharField(max_length=80, blank=True, null=True)
    one_click_purchasing = models.BooleanField(default=False)

    def __str__(self):
        return self.user.get_username()


class Item(models.Model):
    title = models.CharField(max_length=100)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    discount_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    category = models.CharField(choices=CATEGORY_CHOICES, max_length=2)
    label = models.CharField(choices=LABEL_CHOICES, max_length=1)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    image = models.ImageField(upload_to="products/", blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(discount_price__isnull=True) | Q(discount_price__lte=F("price")),
                name="item_discount_not_above_price",
            )
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("core:product", kwargs={"slug": self.slug})

    def get_add_to_cart_url(self):
        return reverse("core:add-to-cart", kwargs={"slug": self.slug})

    def get_remove_from_cart_url(self):
        return reverse("core:remove-from-cart", kwargs={"slug": self.slug})


class OrderItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    ordered = models.BooleanField(default=False)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name="order_item_quantity_gte_1"),
            models.UniqueConstraint(
                fields=("user", "item"),
                condition=Q(ordered=False),
                name="unique_active_user_item",
            ),
        ]

    def __str__(self):
        return f"{self.quantity} of {self.item.title}"

    def get_total_item_price(self):
        return self.quantity * self.item.price

    def get_total_discount_item_price(self):
        if self.item.discount_price is None:
            return self.get_total_item_price()
        return self.quantity * self.item.discount_price

    def get_amount_saved(self):
        return self.get_total_item_price() - self.get_total_discount_item_price()

    def get_final_price(self):
        if self.item.discount_price is not None:
            return self.get_total_discount_item_price()
        return self.get_total_item_price()


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        RECONCILIATION_REQUIRED = "reconciliation_required", "Reconciliation required"

    provider_payment_id = models.CharField(max_length=100, unique=True, blank=True, null=True)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    currency = models.CharField(max_length=3, default="PKR")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    error_code = models.CharField(max_length=64, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="payment_amount_non_negative"),
        ]

    def __str__(self):
        username = self.user.get_username() if self.user else "deleted-user"
        return f"{username}: {self.amount} {self.currency} ({self.status})"


class Coupon(models.Model):
    code = models.CharField(max_length=15, unique=True)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(blank=True, null=True)
    valid_until = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="coupon_amount_non_negative"),
            models.CheckConstraint(
                condition=Q(valid_from__isnull=True)
                | Q(valid_until__isnull=True)
                | Q(valid_until__gt=F("valid_from")),
                name="coupon_valid_window",
            ),
        ]

    def __str__(self):
        return self.code


class Address(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    street_address = models.CharField(max_length=100)
    apartment_address = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=2, choices=PAKISTAN_COUNTRY_CHOICES, default="PK")
    zip = models.CharField(max_length=5, validators=[PAKISTAN_POSTAL_CODE])
    address_type = models.CharField(max_length=1, choices=ADDRESS_CHOICES)
    default = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.get_username()} — {self.get_address_type_display()}"

    class Meta:
        verbose_name_plural = "Addresses"


class Order(models.Model):
    class Status(models.TextChoices):
        CART = "cart", "Cart"
        PAYMENT_PENDING = "payment_pending", "Payment pending"
        PAID = "paid", "Paid"
        FULFILLED = "fulfilled", "Fulfilled"
        REFUND_REQUESTED = "refund_requested", "Refund requested"
        REFUNDED = "refunded", "Refunded"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    ref_code = models.CharField(max_length=20, blank=True, null=True, unique=True)
    items = models.ManyToManyField(OrderItem)
    start_date = models.DateTimeField(auto_now_add=True)
    ordered_date = models.DateTimeField()
    ordered = models.BooleanField(default=False)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.CART)
    shipping_address = models.ForeignKey(
        Address,
        related_name="shipping_orders",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    billing_address = models.ForeignKey(
        Address,
        related_name="billing_orders",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, blank=True, null=True)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, blank=True, null=True)
    being_delivered = models.BooleanField(default=False)
    received = models.BooleanField(default=False)
    refund_requested = models.BooleanField(default=False)
    refund_granted = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user",),
                condition=Q(ordered=False),
                name="one_active_cart_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user.get_username()} — {self.status}"

    def get_total(self):
        total = sum(
            (order_item.get_final_price() for order_item in self.items.select_related("item")),
            Decimal("0.00"),
        )
        if self.coupon_id:
            total -= self.coupon.amount
        return max(total, Decimal("0.00"))


class Refund(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    reason = models.TextField()
    accepted = models.BooleanField(default=False)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Refund {self.pk} for {self.order.ref_code}"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def userprofile_receiver(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        UserProfile.objects.get_or_create(user=instance)
