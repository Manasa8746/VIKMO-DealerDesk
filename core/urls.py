
from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health_check, name="health"),
    path("sync/supplier/", views.sync_supplier, name="sync-supplier"),

    # Products
    path("products/", views.products, name="products"),
    path(
        "products/<str:sku>/",
        views.product_detail,
        name="product-detail",
    ),

    # Inventory
    path(
        "inventory/<str:sku>/",
        views.inventory,
        name="inventory",
    ),

    # Dealers
    path("dealers/", views.dealers, name="dealers"),
    path(
        "dealers/<int:dealer_id>/",
        views.dealer_detail,
        name="dealer-detail",
    ),

    # Orders
    path("orders/", views.orders, name="orders"),
    path(
        "orders/<str:order_number>/",
        views.order_detail,
        name="order-detail",
    ),
    
    path(
        "orders/<str:order_number>/confirm/",
        views.confirm_order,
        name="order-confirm",
    ),
    path(
        "orders/<str:order_number>/cancel/",
        views.cancel_order,
       name="order-cancel",
    ),


    # Forecasting
    path(
        "forecast/<str:sku>/",
        views.forecast_for_sku,
        name="forecast-for-sku",
    ),
    path(
        "reorder-suggestions/",
        views.reorder_suggestions,
        name="reorder-suggestions",
    ),

    # AI Assistant
    path(
        "assistant/chat/",
        views.assistant_chat,
        name="assistant-chat",
    ),
]
