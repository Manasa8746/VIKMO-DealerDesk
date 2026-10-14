
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_FILE = ROOT / "ml" / "forecast.csv"

FORECAST_WEEKS = [
    "2026-09-28",
    "2026-10-05",
    "2026-10-12",
    "2026-10-19",
]


def read_csv(filename):
    with (DATA_DIR / filename).open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        return list(csv.DictReader(file))


lead_times = read_csv("lead_times.csv")
sales = read_csv("sales_history.csv")

# Collect historical weekly sales for each SKU.
weekly_sales = defaultdict(list)

for row in sales:
    sku = row["sku"].strip()
    week = row["week_start"].strip()
    units = float(row["units_sold"])

    weekly_sales[sku].append((week, units))

forecast_rows = []

for item in lead_times:
    sku = item["sku"].strip()

    # Use the latest 12 weeks of available historical sales.
    history = sorted(weekly_sales.get(sku, []))[-12:]

    # Simple baseline: average weekly sales.
    forecast = mean(units for _, units in history) if history else 0.0

    for week in FORECAST_WEEKS:
        forecast_rows.append({
            "sku": sku,
            "week_start": week,
            "forecast_units": round(max(0.0, forecast), 2),
        })

with OUTPUT_FILE.open(
    "w", newline="", encoding="utf-8"
) as file:
    writer = csv.DictWriter(
        file,
        fieldnames=["sku", "week_start", "forecast_units"],
    )
    writer.writeheader()
    writer.writerows(forecast_rows)

print(f"Forecast file created: {OUTPUT_FILE}")
print(f"Total rows: {len(forecast_rows)}")
print(f"Unique SKUs: {len(set(row['sku'] for row in forecast_rows))}")
