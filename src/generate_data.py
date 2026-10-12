"""Simulate the daily reports an Amazon FBA seller downloads from Seller Central.

Each run lands one CSV per report per day under data/raw/<report>/<date>.csv,
the same way files would land in an S3 bucket:

  * orders     - mimics the "All Orders" flat-file report (hyphenated headers,
                 prices as text, occasional duplicate rows, mixed-case ASINs)
  * ads        - mimics the Sponsored Products advertised-product report
  * inventory  - end-of-day FBA inventory snapshot (fulfillable + inbound)

The simulation is stateful: today's inventory starts from yesterday's
snapshot, sales cannot exceed stock, ads stop serving when a SKU is out of
stock, and purchase orders are placed when stock falls below the reorder
point. Every day is seeded from its date, so re-running is reproducible.

Usage:
    python src/generate_data.py                       # fill every missing day up to yesterday (UTC)
    python src/generate_data.py --start 2026-06-14 --end 2026-10-11
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from catalog import CAMPAIGN_TYPES, PRODUCT_COLUMNS, PRODUCTS

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DEFAULT_START = date(2026, 6, 14)

SHIP_STATES = ["CA", "TX", "FL", "NY", "WA", "IL", "PA", "OH", "GA", "NC", "TN", "AZ", "MA", "CO"]
STATE_WEIGHTS = np.array([15, 11, 9, 8, 5, 5, 5, 4, 4, 4, 3, 3, 3, 3], dtype=float)
STATE_WEIGHTS /= STATE_WEIGHTS.sum()

# Day-of-week demand multipliers (Monday=0)
DOW_FACTOR = [1.04, 1.00, 0.98, 0.97, 0.95, 0.96, 1.10]

# Campaign efficiency profiles: (ctr, cpc at a $25 price point, conversion_rate)
# Phrase campaigns are deliberately weaker so the optimization mart has something to find.
CAMPAIGN_PROFILES = {
    "Auto": (0.0035, 0.75, 0.11),
    "Exact": (0.0060, 1.10, 0.15),
    "Phrase": (0.0042, 1.15, 0.08),
}


def sku_cpc_multiplier(sku: str) -> float:
    """Fixed per-SKU competitiveness: some keywords are pricier than others (0.7x - 1.4x)."""
    return 0.7 + (sum(ord(c) * (i + 1) for i, c in enumerate(sku)) % 71) / 100


def products_df() -> pd.DataFrame:
    return pd.DataFrame(PRODUCTS, columns=PRODUCT_COLUMNS)


def campaigns_for(sku: str) -> list[str]:
    """Each SKU runs 2 campaigns; which two is fixed per SKU."""
    idx = sum(ord(c) for c in sku) % 3
    return [CAMPAIGN_TYPES[idx], CAMPAIGN_TYPES[(idx + 1) % 3]]


def season_factor(d: date) -> float:
    """Slow upward trend plus a Q4 ramp starting in October."""
    day_of_year = d.timetuple().tm_yday
    q4_ramp = max(0.0, (day_of_year - 275) / 60) * 0.30
    return 1.0 + q4_ramp


def raw_path(report: str, d: date) -> Path:
    return RAW / report / f"{d.isoformat()}.csv"


def load_previous_inventory(d: date, rng: np.random.Generator, catalog: pd.DataFrame) -> pd.DataFrame:
    prev = raw_path("inventory", d - timedelta(days=1))
    if prev.exists():
        inv = pd.read_csv(prev, dtype={"inbound_eta": "string"})
        return inv.set_index("sku")
    # Cold start: seed opening stock between 20 and 50 days of base demand
    opening = (catalog["base_daily_units"] * rng.uniform(20, 50, len(catalog))).round().astype(int)
    return pd.DataFrame(
        {
            "sku": catalog["sku"],
            "fulfillable_qty": opening,
            "inbound_qty": 0,
            "inbound_eta": pd.Series([pd.NA] * len(catalog), dtype="string"),
        }
    ).set_index("sku")


def amazon_order_id(rng: np.random.Generator) -> str:
    return f"11{rng.integers(1, 5)}-{rng.integers(1_000_000, 9_999_999)}-{rng.integers(1_000_000, 9_999_999)}"


def simulate_day(d: date) -> None:
    rng = np.random.default_rng(int(d.strftime("%Y%m%d")))
    catalog = products_df()
    inv = load_previous_inventory(d, rng, catalog)

    order_rows, ad_rows, inv_rows = [], [], []
    demand_mult = DOW_FACTOR[d.weekday()] * season_factor(d)

    for p in catalog.itertuples(index=False):
        state = inv.loc[p.sku]
        on_hand = int(state["fulfillable_qty"])
        inbound = int(state["inbound_qty"])
        eta = state["inbound_eta"]

        # 1. Receive inbound shipment that arrives today
        if inbound > 0 and pd.notna(eta) and str(eta) <= d.isoformat():
            on_hand += inbound
            inbound, eta = 0, pd.NA

        in_stock = on_hand > 0

        # 2. Advertising: Amazon stops serving ads for out-of-stock listings
        ad_units_wanted = 0
        for camp_type in campaigns_for(p.sku):
            ctr, base_cpc, cvr = CAMPAIGN_PROFILES[camp_type]
            cpc = base_cpc * (p.list_price / 25) * sku_cpc_multiplier(p.sku)
            if in_stock:
                impressions = int(rng.poisson(p.base_daily_units * 260 * demand_mult))
                clicks = int(rng.binomial(impressions, ctr * rng.uniform(0.85, 1.15)))
                spend = round(clicks * cpc * rng.uniform(0.8, 1.2), 2)
                ad_orders = int(rng.binomial(clicks, cvr))
            else:
                impressions = clicks = ad_orders = 0
                spend = 0.0
            ad_units_wanted += ad_orders
            ad_rows.append(
                {
                    "Date": d.isoformat(),
                    "Campaign Name": f"SP / {p.sku} / {camp_type}",
                    "Ad Group Name": f"{p.category} - {camp_type}",
                    "Advertised SKU": p.sku,
                    "Advertised ASIN": p.asin,
                    "Impressions": impressions,
                    "Clicks": clicks,
                    "Spend": spend,
                    "7 Day Total Orders (#)": ad_orders,
                    "7 Day Total Sales": round(ad_orders * p.list_price, 2),
                }
            )

        # 3. Organic demand, capped by available stock together with ad demand
        organic_units = int(rng.poisson(p.base_daily_units * 0.65 * demand_mult))
        units_wanted = organic_units + ad_units_wanted
        units_sold = min(units_wanted, on_hand)

        # 4. Turn units into order lines (most orders are 1 unit, some 2-3)
        remaining = units_sold
        while remaining > 0:
            qty = int(min(remaining, rng.choice([1, 1, 1, 1, 1, 2, 2, 3])))
            remaining -= qty
            ts = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(
                seconds=int(rng.integers(0, 86_400))
            )
            status = "Cancelled" if rng.random() < 0.03 else "Shipped"
            discount = round(p.list_price * qty * 0.10, 2) if rng.random() < 0.08 else 0.0
            asin = p.asin.lower() if rng.random() < 0.02 else p.asin  # messy source data
            order_rows.append(
                {
                    "amazon-order-id": amazon_order_id(rng),
                    "purchase-date": ts.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    "order-status": status,
                    "sales-channel": "Amazon.com",
                    "sku": p.sku,
                    "asin": asin,
                    "quantity": qty,
                    "currency": "USD",
                    "item-price": f"${p.list_price * qty:.2f}",
                    "item-promotion-discount": f"{discount:.2f}",
                    "ship-state": rng.choice(SHIP_STATES, p=STATE_WEIGHTS),
                }
            )
            if status == "Cancelled":
                units_sold -= qty  # cancelled units go back to stock

        on_hand -= units_sold

        # 5. Replenishment: place a PO when stock drops below the reorder point
        reorder_point = p.base_daily_units * (p.lead_time_days + 4)
        if on_hand <= reorder_point and inbound == 0:
            inbound = int(p.base_daily_units * rng.uniform(40, 60))
            delay = int(rng.choice([0, 0, 0, 3, 6, 12]))  # supplier / port delays happen
            eta = (d + timedelta(days=p.lead_time_days + delay)).isoformat()

        inv_rows.append(
            {
                "snapshot_date": d.isoformat(),
                "sku": p.sku,
                "asin": p.asin,
                "fulfillable_qty": on_hand,
                "inbound_qty": inbound,
                "inbound_eta": eta if pd.notna(eta) else "",
            }
        )

    orders = pd.DataFrame(order_rows)
    # Seller Central exports occasionally repeat rows; keep ~1% duplicates for the pipeline to handle
    if len(orders) > 0:
        dupes = orders.sample(frac=0.01, random_state=int(d.strftime("%Y%m%d")))
        orders = pd.concat([orders, dupes]).sort_values("purchase-date")

    for report, frame in (("orders", orders), ("ads", pd.DataFrame(ad_rows)), ("inventory", pd.DataFrame(inv_rows))):
        path = raw_path(report, d)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)


def last_generated_date() -> date | None:
    files = sorted((RAW / "inventory").glob("*.csv"))
    return date.fromisoformat(files[-1].stem) if files else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=date.fromisoformat, help="first date to generate")
    parser.add_argument("--end", type=date.fromisoformat, help="last date to generate (default: yesterday UTC)")
    args = parser.parse_args()

    end = args.end or (datetime.now(timezone.utc).date() - timedelta(days=1))
    last = last_generated_date()
    start = args.start or (last + timedelta(days=1) if last else DEFAULT_START)

    if start > end:
        print(f"Raw data already up to date through {last}. Nothing to generate.")
        return

    d = start
    while d <= end:
        simulate_day(d)
        d += timedelta(days=1)
    print(f"Generated raw reports for {start} -> {end} ({(end - start).days + 1} days)")


if __name__ == "__main__":
    main()
