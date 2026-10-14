
import csv
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Dealer, Product


def read_csv(filename):
    path = settings.DATA_DIR / filename

    if not path.exists():
        raise CommandError(f"Required data file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def get_value(row, key, default=""):
    value = row.get(key, default)
    return str(value if value is not None else default).strip()


def get_money(row, key):
    raw = get_value(row, key, "0") or "0"

    try:
        amount = Decimal(raw)

        if not amount.is_finite():
            raise InvalidOperation

        return amount.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise CommandError(f"Invalid money value for {key}: {raw!r}")


class Command(BaseCommand):
    help = "Import catalogue and dealer CSV data safely and repeatably."

    @transaction.atomic
    def handle(self, *args, **options):
        product_rows = read_csv("catalogue.csv")
        dealer_rows = read_csv("dealers.csv")

        # Validate all product rows before writing to the database.
        products_by_sku = {}

        for row in product_rows:
            sku = get_value(row, "sku")

            if not sku:
                raise CommandError("A catalogue row has an empty SKU.")

            if sku in products_by_sku:
                raise CommandError(f"Duplicate SKU in CSV: {sku}")

            products_by_sku[sku] = {
                "sku": sku,
                "name": get_value(row, "name"),
                "category": get_value(row, "category"),
                "brand": get_value(row, "brand"),
                "vehicle_fitment": get_value(row, "vehicle_fitment"),
                "price": get_money(row, "price"),
                "description": get_value(row, "description"),
            }

        # Validate all dealer rows before writing to the database.
        dealers_by_code = {}

        for row in dealer_rows:
            code = get_value(row, "dealer_code")

            if not code:
                raise CommandError("A dealer row has an empty dealer code.")

            if code in dealers_by_code:
                raise CommandError(f"Duplicate dealer code in CSV: {code}")

            dealers_by_code[code] = {
                "dealer_code": code,
                "name": get_value(row, "name"),
                "city": get_value(row, "city"),
                "phone": get_value(row, "phone"),
                "email": get_value(row, "email"),
                "gstin": get_value(row, "gstin"),
                "credit_limit": get_money(row, "credit_limit"),
            }

        if len(products_by_sku) != 600:
            raise CommandError(
                f"Expected 600 unique products in catalogue.csv; "
                f"found {len(products_by_sku)}."
            )

        if len(dealers_by_code) != 25:
            raise CommandError(
                f"Expected 25 unique dealers in dealers.csv; "
                f"found {len(dealers_by_code)}."
            )

        product_objects = [
            Product(**data, stock=0)
            for data in products_by_sku.values()
        ]

        dealer_objects = [
            Dealer(**data)
            for data in dealers_by_code.values()
        ]

        Product.objects.bulk_create(
            product_objects,
            batch_size=200,
            update_conflicts=True,
            unique_fields=["sku"],
            update_fields=[
                "name",
                "category",
                "brand",
                "vehicle_fitment",
                "price",
                "description",
            ],
        )

        Dealer.objects.bulk_create(
            dealer_objects,
            batch_size=100,
            update_conflicts=True,
            unique_fields=["dealer_code"],
            update_fields=[
                "name",
                "city",
                "phone",
                "email",
                "gstin",
                "credit_limit",
            ],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed complete: processed {len(product_objects)} products "
                f"and {len(dealer_objects)} dealers. "
                f"Database totals: {Product.objects.count()} products, "
                f"{Dealer.objects.count()} dealers."
            )
        )
