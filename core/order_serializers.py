
from decimal import Decimal, ROUND_HALF_UP

from rest_framework import serializers

from .models import Order, OrderItem


TAX_RATE = Decimal("0.18")
TWO_DECIMAL_PLACES = Decimal("0.01")


def money(value):
    """Round a monetary amount to two decimal places."""
    return value.quantize(
        TWO_DECIMAL_PLACES,
        rounding=ROUND_HALF_UP,
    )


class OrderItemSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    line_subtotal = serializers.SerializerMethodField()
    line_tax = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "sku",
            "name",
            "quantity",
            "unit_price",
            "line_subtotal",
            "line_tax",
            "line_total",
        ]

    def get_line_subtotal(self, obj):
        subtotal = obj.unit_price * obj.quantity
        return f"{money(subtotal):.2f}"

    def get_line_tax(self, obj):
        subtotal = obj.unit_price * obj.quantity
        tax = money(subtotal * TAX_RATE)
        return f"{tax:.2f}"

    def get_line_total(self, obj):
        subtotal = obj.unit_price * obj.quantity
        tax = money(subtotal * TAX_RATE)
        return f"{money(subtotal + tax):.2f}"


class OrderSerializer(serializers.ModelSerializer):
    dealer_id = serializers.IntegerField(
        source="dealer.id",
        read_only=True,
    )
    items = OrderItemSerializer(many=True, read_only=True)
    subtotal = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    tax_total = serializers.DecimalField(
        source="tax",
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    grand_total = serializers.DecimalField(
        source="total",
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = Order
        fields = [
            "order_number",
            "dealer_id",
            "status",
            "items",
            "subtotal",
            "tax_total",
            "grand_total",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
