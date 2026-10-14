
from rest_framework import serializers

from .models import Dealer, Product


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "sku",
            "name",
            "category",
            "brand",
            "vehicle_fitment",
            "price",
            "stock",
            "description",
        ]
        read_only_fields = ["stock"]

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Price must be greater than zero."
            )
        return value



class DealerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dealer
        fields = [
            "id",
            "dealer_code",
            "name",
            "city",
            "phone",
            "email",
            "gstin",
            "credit_limit",
        ]
        read_only_fields = ["id"]
        extra_kwargs = {
            "dealer_code": {"validators": []},
        }

    def validate_credit_limit(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "Credit limit cannot be negative."
            )
        return value
