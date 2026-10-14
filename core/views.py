import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

import requests
import csv
import inspect
import math
import uuid
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from statistics import stdev

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .assistant_chat import ask_gemini
from .models import Dealer, Product, Order, OrderItem
from .serializers import ProductSerializer, DealerSerializer


# =========================================================
# COMMON HELPERS
# =========================================================

MONEY = Decimal("0.01")
GST_RATE = Decimal("0.18")


class ContractPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def api_error(code, message, details=None, http_status=400):
    """Return a consistent API error response."""
    return Response(
        {
            "error": {
                "code": code,
                "message": message,
                "details": details if details is not None else [],
            }
        },
        status=http_status,
    )


def money(value):
    """Round monetary values to two decimal places."""
    return Decimal(str(value)).quantize(
        MONEY, rounding=ROUND_HALF_UP
    )


def csv_path(*parts):
    """Build a path relative to the project root."""
    return Path(settings.BASE_DIR).joinpath(*parts)


def read_csv_rows(path):
    """Read a CSV file and return its rows as dictionaries."""
    with open(path, "r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def valid_positive_integer(value):
    """True only for a genuine positive integer, not a boolean."""
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value > 0
    )


def valid_nonnegative_integer(value):
    """True only for an integer >= 0, not a boolean."""
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def paginate_queryset(queryset, request, serializer_class):
    """Apply the common pagination format."""
    paginator = ContractPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = serializer_class(page, many=True)
    return paginator.get_paginated_response(serializer.data)


# =========================================================
# HEALTH CHECK
# =========================================================

@api_view(["GET"])
def health_check(request):
    return Response({"status": "ok"})


# =========================================================
# PRODUCTS
# =========================================================

@api_view(["GET", "POST"])
def products(request):
    """List products with filters or create a product."""

    if request.method == "POST":
        serializer = ProductSerializer(data=request.data)

        if not serializer.is_valid():
            return api_error(
                "VALIDATION_ERROR",
                "Invalid product data.",
                serializer.errors,
            )

        sku = serializer.validated_data.get("sku")

        if Product.objects.filter(sku=sku).exists():
            return api_error(
                "DUPLICATE",
                "Product SKU already exists.",
                http_status=status.HTTP_409_CONFLICT,
            )

        try:
            product = serializer.save(stock=0)
        except IntegrityError:
            return api_error(
                "DUPLICATE",
                "Product SKU already exists.",
                http_status=status.HTTP_409_CONFLICT,
            )

        return Response(
            ProductSerializer(product).data,
            status=status.HTTP_201_CREATED,
        )

    queryset = Product.objects.all().order_by("sku")

    search = request.query_params.get("search", "").strip()
    category = request.query_params.get("category", "").strip()
    vehicle = request.query_params.get("vehicle", "").strip()

    if search:
        queryset = queryset.filter(
            Q(sku__icontains=search)
            | Q(name__icontains=search)
            | Q(brand__icontains=search)
        )

    if category:
        queryset = queryset.filter(category=category)

    if vehicle:
        queryset = queryset.filter(
            vehicle_fitment__icontains=vehicle
        )

    return paginate_queryset(queryset, request, ProductSerializer)


@api_view(["GET", "PATCH"])
def product_detail(request, sku):
    """Retrieve or partially update a product using its SKU."""

    try:
        product = Product.objects.get(sku=sku)
    except Product.DoesNotExist:
        return api_error(
            "NOT_FOUND",
            "Product not found.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        return Response(ProductSerializer(product).data)

    if "sku" in request.data and request.data["sku"] != sku:
        return api_error(
            "VALIDATION_ERROR",
            "SKU cannot be changed.",
        )

    serializer = ProductSerializer(
        product,
        data=request.data,
        partial=True,
    )

    if not serializer.is_valid():
        return api_error(
            "VALIDATION_ERROR",
            "Invalid product data.",
            serializer.errors,
        )

    serializer.save()
    return Response(serializer.data)


# =========================================================
# INVENTORY
# =========================================================

@api_view(["GET", "PUT"])
def inventory(request, sku):
    """Retrieve stock or set the exact stock quantity."""

    try:
        product = Product.objects.get(sku=sku)
    except Product.DoesNotExist:
        return api_error(
            "NOT_FOUND",
            "Product not found.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        return Response({
            "sku": product.sku,
            "name": product.name,
            "current_stock": product.stock,
            "is_in_stock": product.stock > 0,
        })

    quantity = request.data.get("quantity")

    if not valid_nonnegative_integer(quantity):
        return api_error(
            "VALIDATION_ERROR",
            "quantity must be an integer >= 0.",
        )

    product.stock = quantity
    product.save(update_fields=["stock"])

    return Response({
        "sku": product.sku,
        "quantity": product.stock,
    })


# =========================================================
# DEALERS
# =========================================================

@api_view(["GET", "POST"])
def dealers(request):
    """List dealers or create a dealer."""

    if request.method == "POST":
        serializer = DealerSerializer(data=request.data)

        if not serializer.is_valid():
            return api_error(
                "VALIDATION_ERROR",
                "Invalid dealer data.",
                serializer.errors,
            )

        dealer_code = serializer.validated_data.get("dealer_code")

        if Dealer.objects.filter(dealer_code=dealer_code).exists():
            return api_error(
                "DUPLICATE",
                "Dealer code already exists.",
                http_status=status.HTTP_409_CONFLICT,
            )

        try:
            dealer = serializer.save()
        except IntegrityError:
            return api_error(
                "DUPLICATE",
                "Dealer code already exists.",
                http_status=status.HTTP_409_CONFLICT,
            )

        return Response(
            DealerSerializer(dealer).data,
            status=status.HTTP_201_CREATED,
        )

    queryset = Dealer.objects.all().order_by("id")
    return paginate_queryset(queryset, request, DealerSerializer)


@api_view(["GET"])
def dealer_detail(request, dealer_id):
    """Retrieve a dealer using its database ID."""

    try:
        dealer = Dealer.objects.get(pk=dealer_id)
    except (Dealer.DoesNotExist, ValueError, TypeError):
        return api_error(
            "NOT_FOUND",
            "Dealer not found.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    return Response(DealerSerializer(dealer).data)


# =========================================================
# ORDERS
# =========================================================

def order_item_data(order_item):
    """Serialize an order line with GST rounded per line."""

    product = order_item.product
    quantity = order_item.quantity
    unit_price = Decimal(str(order_item.unit_price))

    subtotal = money(unit_price * quantity)
    tax = money(subtotal * GST_RATE)
    total = subtotal + tax

    return {
        "sku": product.sku,
        "name": product.name,
        "quantity": quantity,
        "unit_price": f"{unit_price:.2f}",
        "line_subtotal": f"{subtotal:.2f}",
        "line_tax": f"{tax:.2f}",
        "line_total": f"{total:.2f}",
    }


def order_data(order):
    """Build the documented order response."""

    order_items = (
        OrderItem.objects
        .filter(order=order)
        .select_related("product")
        .order_by("id")
    )

    items = [order_item_data(item) for item in order_items]

    subtotal = sum(
        (Decimal(item["line_subtotal"]) for item in items),
        Decimal("0.00"),
    )
    tax_total = sum(
        (Decimal(item["line_tax"]) for item in items),
        Decimal("0.00"),
    )

    return {
        "order_number": order.order_number,
        "dealer_id": order.dealer_id,
        "status": order.status,
        "items": items,
        "subtotal": f"{subtotal:.2f}",
        "tax_total": f"{tax_total:.2f}",
        "grand_total": f"{subtotal + tax_total:.2f}",
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }


def next_order_number():
    """Create the next daily order number.

    The uniqueness constraint on Order.order_number should remain
    enabled in the database. A conflicting insert is handled below.
    """
    today = timezone.localdate()
    prefix = f"ORD-{today:%Y%m%d}-"

    last_order = (
        Order.objects
        .filter(order_number__startswith=prefix)
        .order_by("-order_number")
        .first()
    )

    sequence = (
        int(last_order.order_number[-4:]) + 1
        if last_order
        else 1
    )

    return f"{prefix}{sequence:04d}"


@api_view(["GET", "POST"])
def orders(request):
    """List orders or create a DRAFT order."""

    if request.method == "GET":
        queryset = Order.objects.all().order_by("-id")

        dealer_id = request.query_params.get("dealer_id")
        order_status = request.query_params.get("status")

        if dealer_id:
            queryset = queryset.filter(dealer_id=dealer_id)

        if order_status:
            queryset = queryset.filter(status=order_status)

        paginator = ContractPagination()
        page = paginator.paginate_queryset(queryset, request)

        return paginator.get_paginated_response([
            order_data(order) for order in page
        ])

    dealer_id = request.data.get("dealer_id")
    items = request.data.get("items")

    if dealer_id in (None, "") or not isinstance(items, list) or not items:
        return api_error(
            "VALIDATION_ERROR",
            "dealer_id and at least one item are required.",
        )

    try:
        dealer = Dealer.objects.get(pk=dealer_id)
    except (Dealer.DoesNotExist, ValueError, TypeError):
        return api_error(
            "VALIDATION_ERROR",
            "Invalid dealer_id.",
        )

    seen_skus = set()
    validated_items = []

    for item in items:
        if not isinstance(item, dict):
            return api_error(
                "VALIDATION_ERROR",
                "Each item must contain sku and quantity.",
            )

        sku = item.get("sku")
        quantity = item.get("quantity")

        if not isinstance(sku, str) or not sku.strip():
            return api_error(
                "VALIDATION_ERROR",
                "Each item requires a valid SKU.",
            )

        sku = sku.strip()

        if sku in seen_skus:
            return api_error(
                "VALIDATION_ERROR",
                f"Duplicate SKU: {sku}",
            )

        if not valid_positive_integer(quantity):
            return api_error(
                "VALIDATION_ERROR",
                "Quantity must be an integer greater than zero.",
            )

        seen_skus.add(sku)

        try:
            product = Product.objects.get(sku=sku)
        except Product.DoesNotExist:
            return api_error(
                "VALIDATION_ERROR",
                f"Unknown SKU: {sku}",
            )

        validated_items.append((product, quantity))

    try:
        with transaction.atomic():
            order = Order.objects.create(
                order_number=next_order_number(),
                dealer=dealer,
                status="DRAFT",
                subtotal=Decimal("0.00"),
                tax=Decimal("0.00"),
                total=Decimal("0.00"),
            )

            subtotal = Decimal("0.00")
            tax_total = Decimal("0.00")

            for product, quantity in validated_items:
                unit_price = Decimal(str(product.price))
                line_subtotal = money(unit_price * quantity)
                line_tax = money(line_subtotal * GST_RATE)

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    unit_price=unit_price,
                )

                subtotal += line_subtotal
                tax_total += line_tax

            order.subtotal = subtotal
            order.tax = tax_total
            order.total = subtotal + tax_total
            order.save(
                update_fields=[
                    "subtotal",
                    "tax",
                    "total",
                    "updated_at",
                ]
            )

    except IntegrityError:
        return api_error(
            "ORDER_CREATION_ERROR",
            "Unable to create the order due to a database conflict. Please retry.",
            http_status=status.HTTP_409_CONFLICT,
        )

    return Response(
        order_data(order),
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
def order_detail(request, order_number):
    """Retrieve an order using its order number."""

    try:
        order = Order.objects.get(order_number=order_number)
    except Order.DoesNotExist:
        return api_error(
            "NOT_FOUND",
            "Order not found.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    return Response(order_data(order))


@api_view(["POST"])
def confirm_order(request, order_number):
    """Confirm a draft order and deduct its items from stock."""

    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(
                order_number=order_number
            )

            if order.status != Order.Status.DRAFT:
                return api_error(
                    "INVALID_TRANSITION",
                    "Only draft orders can be confirmed.",
                    http_status=status.HTTP_409_CONFLICT,
                )

            items = list(
                order.items.select_related("product").all()
            )

            # Lock products in a consistent order.
            products = {}
            for item in sorted(items, key=lambda x: x.product.sku):
                product = Product.objects.select_for_update().get(
                    pk=item.product_id
                )
                products[item.product_id] = product

            # Check every item's stock before changing anything.
            for item in items:
                product = products[item.product_id]
                if product.stock < item.quantity:
                    return api_error(
                        "INSUFFICIENT_STOCK",
                        f"Insufficient stock for {product.sku}.",
                        http_status=status.HTTP_409_CONFLICT,
                    )

            for item in items:
                product = products[item.product_id]
                product.stock -= item.quantity
                product.save(update_fields=["stock"])

            order.status = Order.Status.CONFIRMED
            order.save(update_fields=["status", "updated_at"])

    except Order.DoesNotExist:
        return api_error(
            "NOT_FOUND",
            "Order not found.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    return Response(order_data(order))


@api_view(["POST"])
def cancel_order(request, order_number):
    """Cancel an order and restore stock if it was confirmed."""

    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(
                order_number=order_number
            )

            if order.status == Order.Status.CANCELLED:
                return api_error(
                    "INVALID_TRANSITION",
                    "Order is already cancelled.",
                    http_status=status.HTTP_409_CONFLICT,
                )

            if order.status == Order.Status.CONFIRMED:
                items = list(
                    order.items.select_related("product").all()
                )

                products = {}
                for item in sorted(items, key=lambda x: x.product.sku):
                    product = Product.objects.select_for_update().get(
                        pk=item.product_id
                    )
                    products[item.product_id] = product

                for item in items:
                    product = products[item.product_id]
                    product.stock += item.quantity
                    product.save(update_fields=["stock"])

            order.status = Order.Status.CANCELLED
            order.save(update_fields=["status", "updated_at"])

    except Order.DoesNotExist:
        return api_error(
            "NOT_FOUND",
            "Order not found.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    return Response(order_data(order))



# =========================================================
# FORECAST
# =========================================================

@api_view(["GET"])
def forecast_for_sku(request, sku):
    """Return up to four weekly forecast rows for a known SKU."""

    try:
        product = Product.objects.get(sku=sku)
    except Product.DoesNotExist:
        return api_error(
            "NOT_FOUND",
            "Product not found.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    forecast_path = csv_path("ml", "forecast.csv")

    try:
        rows = read_csv_rows(forecast_path)
        forecast_rows = []

        for row in rows:
            if row.get("sku") != product.sku:
                continue

            week_start = row.get("week_start")
            units = row.get("forecast_units")

            if not week_start or units in (None, ""):
                continue

            forecast_rows.append({
                "week_start": week_start,
                "forecast_units": float(units),
            })

    except (OSError, ValueError, KeyError):
        return api_error(
            "FORECAST_ERROR",
            "Unable to read forecast data.",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    forecast_rows.sort(key=lambda row: row["week_start"])

    if not forecast_rows:
        return api_error(
            "NOT_FOUND",
            "No forecast available for this SKU.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    return Response({
        "sku": product.sku,
        "forecast": forecast_rows[:4],
    })


# =========================================================
# REORDER SUGGESTIONS
# =========================================================

@api_view(["GET"])
def reorder_suggestions(request):
    """Calculate lead-time demand, safety stock, and reorder quantity."""

    forecast_path = csv_path("ml", "forecast.csv")
    lead_times_path = csv_path("data", "lead_times.csv")
    sales_history_path = csv_path("data", "sales_history.csv")

    try:
        forecast_rows = read_csv_rows(forecast_path)
        lead_time_rows = read_csv_rows(lead_times_path)
        sales_rows = read_csv_rows(sales_history_path)

        # SKU -> ordered weekly forecast values.
        forecasts = defaultdict(list)

        for row in forecast_rows:
            sku = (row.get("sku") or "").strip()
            if not sku:
                continue

            week_start = row.get("week_start", "")
            units = float(row.get("forecast_units") or 0)

            forecasts[sku].append((week_start, units))

        for sku in forecasts:
            forecasts[sku].sort(key=lambda value: value[0])

        # SKU -> lead time in weeks.
        lead_times = {}

        for row in lead_time_rows:
            sku = (row.get("sku") or "").strip()
            raw_lead_time = row.get("lead_time_weeks")

            if not sku or raw_lead_time in (None, ""):
                continue

            lead_time = int(float(raw_lead_time))

            if lead_time < 1:
                continue

            lead_times[sku] = lead_time

        # SKU -> historical weekly sales.
        sales_history = defaultdict(list)

        for row in sales_rows:
            sku = (row.get("sku") or "").strip()
            raw_units = row.get("units_sold")

            if not sku or raw_units in (None, ""):
                continue

            sales_history[sku].append(float(raw_units))

    except (OSError, ValueError, KeyError, TypeError):
        return api_error(
            "REORDER_DATA_ERROR",
            "Unable to read or validate reorder input data.",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    results = []

    # Do not create products from CSV entries. Only suggest reorders
    # for SKUs that really exist in the product database.
    products_by_sku = {
        product.sku: product
        for product in Product.objects.all()
    }

    for sku in sorted(forecasts):
        product = products_by_sku.get(sku)

        if product is None:
            continue

        lead_time = lead_times.get(sku)

        # A missing lead time means we cannot calculate a valid
        # lead-time demand, so omit that suggestion.
        if lead_time is None:
            continue

        weekly_forecasts = forecasts[sku]
        lead_time_demand = math.ceil(
            sum(units for _, units in weekly_forecasts[:lead_time])
        )

        recent_sales = sales_history.get(sku, [])[-12:]

        # Sample standard deviation requires at least two values.
        sigma = stdev(recent_sales) if len(recent_sales) >= 2 else 0.0

        safety_stock = math.ceil(
            1.65 * sigma * math.sqrt(lead_time)
        )

        reorder_point = lead_time_demand + safety_stock
        reorder_qty = max(
            0,
            reorder_point - int(product.stock),
        )

        results.append({
            "sku": sku,
            "current_stock": product.stock,
            "lead_time_weeks": lead_time,
            "lead_time_demand": lead_time_demand,
            "safety_stock": safety_stock,
            "reorder_point": reorder_point,
            "reorder_qty": reorder_qty,
        })

    return Response({"results": results})


# =========================================================
# AI ASSISTANT
# =========================================================

def call_assistant_service(message, dealer_id, session_id):
    """Call ask_gemini using the keyword arguments its function supports.

    This avoids assuming a particular ask_gemini signature.
    """
    signature = inspect.signature(ask_gemini)
    parameters = signature.parameters

    values = {
        "message": message,
        "user_message": message,
        "prompt": message,
        "dealer_id": dealer_id,
        "session_id": session_id,
    }

    accepts_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )

    if accepts_kwargs:
        return ask_gemini(
            message=message,
            dealer_id=dealer_id,
            session_id=session_id,
        )

    kwargs = {
        name: values[name]
        for name, parameter in parameters.items()
        if name in values
        and parameter.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    }

    required_unknown = [
        name
        for name, parameter in parameters.items()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
        and name not in kwargs
    ]

    if required_unknown:
        raise TypeError(
            "Unsupported required ask_gemini parameters: "
            + ", ".join(required_unknown)
        )

    return ask_gemini(**kwargs)


@api_view(["POST"])
def assistant_chat(request):
    """Send a dealer's message to the AI assistant."""

    dealer_id = request.data.get("dealer_id")
    message = request.data.get("message")
    session_id = request.data.get("session_id") or str(uuid.uuid4())

    if dealer_id in (None, ""):
        return api_error(
            "VALIDATION_ERROR",
            "dealer_id is required.",
        )

    if not isinstance(message, str) or not message.strip():
        return api_error(
            "VALIDATION_ERROR",
            "message must be a non-empty string.",
        )

    try:
        dealer = Dealer.objects.get(pk=dealer_id)
    except (Dealer.DoesNotExist, ValueError, TypeError):
        return api_error(
            "VALIDATION_ERROR",
            "Invalid dealer_id.",
        )

    try:
        result = call_assistant_service(
            message=message.strip(),
            dealer_id=dealer.pk,
            session_id=str(session_id),
        )

        if isinstance(result, str):
            reply = result
            cited_skus = []
            tool_calls = []
            actions = []

        elif isinstance(result, dict):
            reply = (
                result.get("reply")
                or result.get("response")
                or result.get("text")
                or ""
            )
            cited_skus = result.get("cited_skus", [])
            tool_calls = result.get("tool_calls", [])
            actions = result.get("actions", [])

        else:
            reply = str(result)
            cited_skus = []
            tool_calls = []
            actions = []

        return Response({
            "session_id": str(session_id),
            "reply": reply,
            "cited_skus": cited_skus,
            "tool_calls": tool_calls,
            "actions": actions,
        })

    except Exception:
        # Keep server-side details out of the public API response.
        # Check the terminal logs for the underlying exception.
        import logging
        logging.getLogger(__name__).exception(
            "Assistant request failed for dealer_id=%s",
            dealer.pk,
        )

        return api_error(
            "ASSISTANT_ERROR",
            "The assistant could not process this message. Please try again.",
            http_status=status.HTTP_502_BAD_GATEWAY,
        )
    


@api_view(["POST"])
def sync_supplier(request):
    """Fetch supplier pages and safely upsert valid product records."""
    base_url = settings.SUPPLIER_API_URL.rstrip("/")
    api_key = settings.SUPPLIER_API_KEY

    if not api_key:
        return api_error(
            "SUPPLIER_CONFIG_ERROR",
            "Supplier API key is not configured.",
            http_status=status.HTTP_502_BAD_GATEWAY,
        )

    url = f"{base_url}/v1/products"
    headers = {"X-Api-Key": api_key}
    cursor = None
    pages_fetched = 0
    requests_made = 0
    records = []
    seen_cursors = set()

    # Fetch every page before making database changes.
    try:
        while True:
            params = {"limit": 20}
            if cursor:
                params["cursor"] = cursor

            response = None

            for attempt in range(5):
                requests_made += 1
                response = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=(3, 10),
                )

                if response.status_code == 200:
                    break

                if response.status_code not in (429, 500, 502, 503, 504):
                    return api_error(
                        "SUPPLIER_ERROR",
                        f"Supplier returned HTTP {response.status_code}.",
                        http_status=status.HTTP_502_BAD_GATEWAY,
                    )

                if attempt < 4:
                    retry_after = response.headers.get("Retry-After", "")
                    try:
                        delay = min(max(float(retry_after), 0), 3)
                    except (ValueError, TypeError):
                        delay = 0.5 * (2 ** attempt)
                    time.sleep(delay)

            if response is None or response.status_code != 200:
                return api_error(
                    "SUPPLIER_UNAVAILABLE",
                    "Supplier request failed after retries; no products were changed.",
                    http_status=status.HTTP_502_BAD_GATEWAY,
                )

            try:
                payload = response.json()
            except ValueError:
                return api_error(
                    "SUPPLIER_ERROR",
                    "Supplier returned invalid JSON.",
                    http_status=status.HTTP_502_BAD_GATEWAY,
                )

            if not isinstance(payload, dict) or not isinstance(
                payload.get("items"), list
            ):
                return api_error(
                    "SUPPLIER_ERROR",
                    "Supplier response has an invalid format.",
                    http_status=status.HTTP_502_BAD_GATEWAY,
                )

            records.extend(payload["items"])
            pages_fetched += 1

            cursor = payload.get("next_cursor")
            if not cursor:
                break

            if not isinstance(cursor, str) or cursor in seen_cursors:
                return api_error(
                    "SUPPLIER_ERROR",
                    "Supplier returned a repeated or invalid cursor.",
                    http_status=status.HTTP_502_BAD_GATEWAY,
                )
            seen_cursors.add(cursor)

            if pages_fetched >= 100:
                return api_error(
                    "SUPPLIER_ERROR",
                    "Supplier pagination exceeded the safety limit.",
                    http_status=status.HTTP_502_BAD_GATEWAY,
                )

    except requests.RequestException:
        return api_error(
            "SUPPLIER_UNAVAILABLE",
            "Could not reach the supplier; no products were changed.",
            http_status=status.HTTP_502_BAD_GATEWAY,
        )

    # Validate records and resolve duplicate SKUs before writing.
    latest_by_sku = {}
    rejected = []

    for index, row in enumerate(records):
        if not isinstance(row, dict):
            rejected.append({
                "index": index,
                "reason": "Record must be an object.",
            })
            continue

        sku = str(row.get("sku") or "").strip()
        name = str(row.get("name") or "").strip()

        if not sku or len(sku) > 50:
            rejected.append({
                "index": index,
                "sku": sku,
                "reason": "Missing or invalid SKU.",
            })
            continue

        if not name or len(name) > 255:
            rejected.append({
                "index": index,
                "sku": sku,
                "reason": "Missing or invalid product name.",
            })
            continue

        try:
            raw_price = str(row.get("price", "")).strip()
            price = Decimal(raw_price)

            if not price.is_finite() or price < 0:
                raise InvalidOperation

            if price.as_tuple().exponent < -2:
                raise InvalidOperation

            price = price.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            rejected.append({
                "index": index,
                "sku": sku,
                "reason": "Price must be a non-negative amount with at most 2 decimals.",
            })
            continue

        updated_at = str(row.get("updated_at") or "")

        # Keep the latest supplier version for duplicate SKUs.
        previous = latest_by_sku.get(sku)
        if previous is None or updated_at >= previous.get("updated_at", ""):
            latest_by_sku[sku] = {
                "sku": sku,
                "name": name,
                "category": str(row.get("category") or "")[:100],
                "brand": str(row.get("brand") or "")[:100],
                "vehicle_fitment": str(row.get("vehicle_fitment") or ""),
                "description": str(row.get("description") or ""),
                "price": price,
                "updated_at": updated_at,
            }

    created = 0
    updated = 0
    unchanged = 0

    try:
        with transaction.atomic():
            for sku, values in latest_by_sku.items():
                product = Product.objects.filter(sku=sku).first()

                if product is None:
                    Product.objects.create(
                        sku=sku,
                        name=values["name"],
                        category=values["category"],
                        brand=values["brand"],
                        vehicle_fitment=values["vehicle_fitment"],
                        description=values["description"],
                        price=values["price"],
                        stock=0,
                    )
                    created += 1
                    continue

                fields = [
                    "name",
                    "category",
                    "brand",
                    "vehicle_fitment",
                    "description",
                    "price",
                ]

                changed_fields = [
                    field for field in fields
                    if getattr(product, field) != values[field]
                ]

                if not changed_fields:
                    unchanged += 1
                    continue

                for field in changed_fields:
                    setattr(product, field, values[field])

                product.save(update_fields=changed_fields)
                updated += 1

    except Exception:
        import logging
        logging.getLogger(__name__).exception("Supplier sync failed")
        return api_error(
            "SUPPLIER_SYNC_ERROR",
            "Supplier data could not be saved; database changes were rolled back.",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "rejected": rejected,
        "pages_fetched": pages_fetched,
        "requests_made": requests_made,
    })


