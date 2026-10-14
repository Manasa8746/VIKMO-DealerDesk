
from decimal import Decimal

from django.db import transaction

from .models import Dealer, Product, Order, OrderItem


def search_parts(query, limit=5):
    """Search parts by SKU, name, brand, category, or vehicle fitment."""
    query = str(query).strip()

    if not query:
        return {"results": []}

    products = Product.objects.filter(
        __import__("django").db.models.Q(sku__icontains=query)
        | __import__("django").db.models.Q(name__icontains=query)
        | __import__("django").db.models.Q(brand__icontains=query)
        | __import__("django").db.models.Q(category__icontains=query)
        | __import__("django").db.models.Q(
            vehicle_fitment__icontains=query
        )
    ).order_by("sku")[:min(max(int(limit), 1), 10)]

    return {
        "results": [
            {
                "sku": p.sku,
                "name": p.name,
                "brand": p.brand,
                "category": p.category,
                "vehicle_fitment": p.vehicle_fitment,
                "price": str(p.price),
                "stock": p.stock,
            }
            for p in products
        ]
    }


def check_stock(sku):
    """Return the current price and stock from PostgreSQL."""
    product = Product.objects.filter(sku=sku).first()

    if product is None:
        return {"error": f"Product SKU '{sku}' was not found."}

    return {
        "sku": product.sku,
        "name": product.name,
        "price": str(product.price),
        "stock": product.stock,
    }


def create_draft_order(dealer_id, items):
    """Create a DRAFT order after validating its items."""
    if not isinstance(dealer_id, int) or isinstance(dealer_id, bool):
        return {"error": "dealer_id must be an integer."}

    if not isinstance(items, list) or not items:
        return {"error": "At least one order item is required."}

    dealer = Dealer.objects.filter(id=dealer_id).first()

    if dealer is None:
        return {"error": "Dealer was not found."}

    seen_skus = set()
    validated = []

    for item in items:
        if not isinstance(item, dict):
            return {"error": "Each item must contain sku and quantity."}

        sku = item.get("sku")
        quantity = item.get("quantity")

        if not isinstance(sku, str) or not sku.strip():
            return {"error": "Each item needs a valid SKU."}

        sku = sku.strip()

        if sku in seen_skus:
            return {"error": f"Duplicate SKU '{sku}'."}
        seen_skus.add(sku)

        if (
            not isinstance(quantity, int)
            or isinstance(quantity, bool)
            or quantity < 1
        ):
            return {"error": f"Invalid quantity for SKU '{sku}'."}

        product = Product.objects.filter(sku=sku).first()

        
        if product is None:
            return {"error": f"Product SKU '{sku}' was not found."}

        if quantity > product.stock:
            return {
                "error": (
                    f"Insufficient stock for SKU '{sku}'. "
                    f"Available: {product.stock}, requested: {quantity}."
                )
            }

        validated.append((product, quantity))

    subtotal = sum(
        (p.price * qty for p, qty in validated),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))

    tax = (subtotal * Decimal("0.18")).quantize(Decimal("0.01"))
    total = subtotal + tax

    import uuid

    with transaction.atomic():
        order = Order.objects.create(
            order_number=f"ORD-{uuid.uuid4().hex[:12].upper()}",
            dealer=dealer,
            status=Order.Status.DRAFT,
            subtotal=subtotal,
            tax=tax,
            total=total,
        )

        OrderItem.objects.bulk_create([
            OrderItem(
                order=order,
                product=product,
                quantity=quantity,
                unit_price=product.price,
            )
            for product, quantity in validated
        ])

    return {
        "order_number": order.order_number,
        "status": order.status,
        "subtotal": str(subtotal),
        "tax": str(tax),
        "grand_total": str(total),
    }
