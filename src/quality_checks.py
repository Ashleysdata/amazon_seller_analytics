"""Data quality tests, in the spirit of dbt tests.

Each check is a SQL query that returns the rows that FAIL the rule.
Zero rows returned means the check passes.
  - error: stops the pipeline (bad data must not reach the dashboard)
  - warn:  reported in the run log, pipeline continues
"""

from __future__ import annotations

import duckdb

CHECKS = [
    # (name, severity, sql returning failing rows)
    (
        "orders: order_id + sku is unique after dedup",
        "error",
        "select order_id, sku from stg_orders group by all having count(*) > 1",
    ),
    (
        "orders: no null keys",
        "error",
        "select * from stg_orders where order_id is null or sku is null or order_date is null",
    ),
    (
        "orders: every sku exists in dim_product",
        "error",
        "select distinct o.sku from stg_orders o anti join dim_product p using (sku)",
    ),
    (
        "orders: prices are positive",
        "error",
        "select * from stg_orders where gross_sales <= 0 or net_sales < 0",
    ),
    (
        "ads: clicks never exceed impressions",
        "error",
        "select * from stg_ads where clicks > impressions",
    ),
    (
        "ads: spend is non-negative",
        "error",
        "select * from stg_ads where spend < 0",
    ),
    (
        "inventory: quantities are non-negative",
        "error",
        "select * from stg_inventory where fulfillable_qty < 0 or inbound_qty < 0",
    ),
    (
        "inventory: one snapshot per sku per day",
        "error",
        "select snapshot_date, sku from stg_inventory group by all having count(*) > 1",
    ),
    (
        "completeness: every day has a row for every sku",
        "error",
        """
        select snapshot_date, count(*) as skus
        from stg_inventory group by snapshot_date
        having count(*) <> (select count(*) from dim_product)
        """,
    ),
    (
        "freshness: orders and inventory end on the same day",
        "warn",
        """
        select (select max(order_date) from stg_orders) as orders_through,
               (select max(snapshot_date) from stg_inventory) as inventory_through
        where (select max(order_date) from stg_orders) <> (select max(snapshot_date) from stg_inventory)
        """,
    ),
    (
        "anomaly: daily net sales within 50% of the trailing 7-day average",
        "warn",
        """
        select date, net_sales, net_sales_7d_avg
        from mart_daily_kpis
        where date = (select max(date) from mart_daily_kpis)
          and abs(net_sales - net_sales_7d_avg) > 0.5 * net_sales_7d_avg
        """,
    ),
]


def run_checks(con: duckdb.DuckDBPyConnection) -> list[dict]:
    results = []
    for name, severity, sql in CHECKS:
        failing = con.execute(f"select count(*) from ({sql})").fetchone()[0]
        status = "PASS" if failing == 0 else ("FAIL" if severity == "error" else "WARN")
        results.append({"check": name, "severity": severity, "failing_rows": failing, "status": status})
        print(f"  [{status}] {name}" + (f"  ({failing} rows)" if failing else ""))
    return results
