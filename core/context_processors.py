from .views import _anonymous_cart_data


def cart_summary(request):
    """Expose a small, reusable cart count to every template."""
    if request.user.is_authenticated:
        from .models import Order

        order = Order.objects.filter(user=request.user, ordered=False).first()
        count = sum(item.quantity for item in order.items.all()) if order else 0
    else:
        count = sum(_anonymous_cart_data(request).values())
    return {"cart_item_count": count}
