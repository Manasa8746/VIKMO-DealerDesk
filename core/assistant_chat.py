
import os
import re
import time

from django.conf import settings
from google import genai
from google.genai import types

from .assistant import search_parts, check_stock, create_draft_order


PRIMARY_MODEL = "gemini-flash-lite-latest"
FALLBACK_MODEL = "gemini-3-flash-preview"


def get_gemini_client():
    """Create the Gemini API client using the configured API key."""
    settings_key = getattr(settings, "GEMINI_API_KEY", None)
    env_key = os.getenv("GEMINI_API_KEY")
    api_key = settings_key or env_key

    if not api_key:
        raise RuntimeError(
            "Gemini API key is missing. Configure GEMINI_API_KEY "
            "in your environment or Django settings."
        )

    return genai.Client(api_key=api_key)


def search_parts_tool(query: str, limit: int = 5) -> dict:
    """Search the catalogue for matching vehicle parts."""
    return search_parts(query, limit)


def check_stock_tool(sku: str) -> dict:
    """Check the current stock and price for a product SKU."""
    return check_stock(sku)


def create_draft_order_tool(
    dealer_id: int,
    items: list[dict],
) -> dict:
    """Create a draft order for a dealer."""
    return create_draft_order(dealer_id, items)


TOOLS = [
    search_parts_tool,
    check_stock_tool,
    create_draft_order_tool,
]


def ask_gemini(message: str, dealer_id: int) -> dict:
    """Send a message to Gemini and return its response and metadata."""
    client = get_gemini_client()

    prompt = (
        f"The current dealer ID is {dealer_id}. "
        "You are VIKMO DealerDesk, a helpful vehicle-parts assistant. "
        "Use tools for product searches, stock, prices, and draft orders. "
        "Never invent stock, prices, or product details. "
        "Display all prices and monetary amounts in Indian rupees (₹), "
        "not dollars ($). "
        "Only create DRAFT orders. Never confirm an order as placed "
        "unless the draft-order tool succeeds. "
        "Ask for missing information before creating an order. "
        "Check product stock before creating an order. "
        "Politely decline unrelated requests.\n\n"
        f"Dealer message: {message}"
    )

    config = types.GenerateContentConfig(
    tools=TOOLS,
    automatic_function_calling=types.AutomaticFunctionCallingConfig(
        maximum_remote_calls=2
    ),
    temperature=0.2,
)

    
    last_error = None

    for model in [PRIMARY_MODEL, FALLBACK_MODEL]:
        for attempt in range(2):
            try:
                chat = client.chats.create(
                    model=model,
                    config=config,
                )

                print(
                    f"[Gemini] Sending request to model: {model}",
                    flush=True,
                )
                start_time = time.time()

                response = chat.send_message(prompt)

                print(
                    f"[Gemini] Response received in "
                    f"{time.time() - start_time:.1f}s",
                    flush=True,
                )


                reply = response.text or (
               "I couldn't generate a response. Please try again."
                )

                print("[Gemini] Reply extracted; processing tool history", flush=True)

                history = chat.get_history()
                print("[Gemini] History retrieved", flush=True)
                tool_calls = []

                # Collect the tool calls made during this conversation.
                for content in history:
                    for part in (
                        getattr(content, "parts", None) or []
                    ):
                        function_call = getattr(
                            part, "function_call", None
                        )

                        if function_call and function_call.name:
                            tool_calls.append({
                                "name": function_call.name,
                                "args": dict(
                                    function_call.args or {}
                                ),
                            })

                # Extract SKUs mentioned in the assistant's reply.
                
                # Extract complete SKUs from the reply and tool calls.
                sku_pattern = r"(?<![A-Z0-9-])[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d{3,}(?![A-Z0-9-])"

                cited_skus_set = set(
                    re.findall(sku_pattern, reply)
                )

                for call in tool_calls:
                    args = call.get("args", {})
                    sku = args.get("sku")

                    if isinstance(sku, str) and re.fullmatch(
                        sku_pattern, sku
                    ):
                        cited_skus_set.add(sku)

                    items = args.get("items", [])

                    if isinstance(items, list):
                        for item in items:
                            if not isinstance(item, dict):
                                continue

                            item_sku = item.get("sku", "")

                            if isinstance(item_sku, str) and re.fullmatch(
                                sku_pattern, item_sku
                            ):
                                cited_skus_set.add(item_sku)

                cited_skus = sorted(cited_skus_set)

                return {
                    "reply": reply,
                    "tool_calls": tool_calls,
                    "cited_skus": cited_skus,
                    "actions": [],
                }

            except Exception as exc:
                last_error = exc
                print(f"[Gemini] {type(exc).__name__}: {exc}", flush=True)
                error_text = str(exc).lower()

                temporary_error = any(
                    term in error_text
                    for term in (
                        "503",
                        "unavailable",
                        "high demand",
                        "429",
                        "resource_exhausted",
                        "500",
                        "internal",
                        "timeout",
                        "timed out",
                    )
                )

                if temporary_error and attempt == 0:
                    time.sleep(2)
                    continue

                break

    raise RuntimeError(
        "Gemini models failed. Last error: "
        f"{type(last_error).__name__}: {last_error}"
    ) from last_error
