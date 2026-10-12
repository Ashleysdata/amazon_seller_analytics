"""Transform raw Seller Central reports into analytics marts.

Steps:
  1. Load the product catalog as a seed table
  2. Run SQL models in order: staging -> marts (DuckDB, in the style of dbt)
  3. Run data quality checks; any error-level failure stops the run
  4. Export marts to data/marts/*.csv
  5. Render the dashboard chart and refresh the KPI block in README.md
  6. Append one line to data/run_log.csv

The warehouse is rebuilt from raw files on every run (full refresh), so the
pipeline is idempotent: running it twice produces the same result.
"""

from __future__ import annotations

import sys 
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from catalog import PRODUCT_COLUMNS, PRODUCTS, REFERRAL_FEE_RATE  # noqa: E402
from quality_checks import run_checks  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"
RAW_DIR = ROOT / "data" / "raw"
MARTS_DIR = ROOT / "data" / "marts"
REPORTS_DIR = ROOT / "reports"
README = ROOT / "README.md"
RUN_LOG = ROOT / "data" / "run_log.csv"

MART_TABLES = ["dim_product", "fct_daily_sku", "mart_daily_kpis", "mart_campaign_actions", "mart_inventory_health"]

# Chart palette (validated reference palette, light mode)
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
SERIES_BLUE = "#2a78d6"
SERIES_ORANGE = "#eb6834"
RAW_LINE = "#b9c9dd"


def run_sql_models(con: duckdb.DuckDBPyConnection) -> None:
    params = {"raw_dir": RAW_DIR.as_posix(), "referral_fee_rate": REFERRAL_FEE_RATE}
    for layer in ("staging", "marts"):
        for path in sorted((SQL_DIR / layer).glob("*.sql")):
            con.execute(path.read_text().format(**params))
            print(f"  built {layer}/{path.name}")


def render_chart(kpis: pd.DataFrame) -> Path:
    # Skip the first 6 days: a 7-day rolling metric is not meaningful until it has 7 days of data
    kpis = kpis.iloc[6:].copy()
    kpis["date"] = pd.to_datetime(kpis["date"])

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 6.2), sharex=True, gridspec_kw={"height_ratios": [2, 1]}, facecolor=SURFACE
    )

    # Panel 1: net sales (daily, light) with 7-day average (bold)
    ax1.plot(kpis["date"], kpis["net_sales"], color=RAW_LINE, linewidth=1, label="Daily")
    ax1.plot(kpis["date"], kpis["net_sales_7d_avg"], color=SERIES_BLUE, linewidth=2, label="7-day average")
    ax1.set_title("Net sales (USD)", loc="left", color=TEXT_PRIMARY, fontsize=11, fontweight="bold")
    ax1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"${v / 1000:.1f}k"))
    ax1.legend(loc="lower right", bbox_to_anchor=(1, 1.0), ncol=2, frameon=False, labelcolor=TEXT_SECONDARY)
    last = kpis.iloc[-1]
    ax1.annotate(
        f"${last['net_sales_7d_avg']:,.0f}",
        (last["date"], last["net_sales_7d_avg"]),
        xytext=(6, 0), textcoords="offset points", va="center", color=TEXT_PRIMARY, fontsize=9,
    )

    # Panel 2: 7-day TACoS. Separate panel instead of a second y-axis.
    ax2.plot(kpis["date"], kpis["tacos_7d"] * 100, color=SERIES_ORANGE, linewidth=2)
    ax2.set_title("TACoS, 7-day (ad spend / total sales, %)", loc="left", color=TEXT_PRIMARY, fontsize=11, fontweight="bold")
    ax2.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(1))
    ax2.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax2.annotate(
        f"{last['tacos_7d'] * 100:.1f}%",
        (last["date"], last["tacos_7d"] * 100),
        xytext=(6, 0), textcoords="offset points", va="center", color=TEXT_PRIMARY, fontsize=9,
    )

    for ax in (ax1, ax2):
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.tick_params(colors=TEXT_SECONDARY, length=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
    ax2.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %d"))

    fig.suptitle(
        f"Northbay Home - Amazon US seller account, data through {last['date']:%Y-%m-%d}",
        x=0.01, ha="left", color=TEXT_SECONDARY, fontsize=9,
    )
    fig.tight_layout()
    out = REPORTS_DIR / "dashboard.png"
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return out


def money(v: float) -> str:
    return f"${v:,.0f}"


def pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def build_kpi_markdown(con: duckdb.DuckDBPyConnection) -> str:
    k = con.execute(
        """
        with last7 as (select * from mart_daily_kpis where date > (select max(date) from mart_daily_kpis) - 7),
             prev7 as (select * from mart_daily_kpis
                       where date <= (select max(date) from mart_daily_kpis) - 7
                         and date >  (select max(date) from mart_daily_kpis) - 14)
        select
            (select max(date) from mart_daily_kpis)                          as as_of,
            (select sum(net_sales) from last7)                               as sales_7d,
            (select sum(net_sales) from prev7)                               as sales_prev_7d,
            (select sum(ad_spend) / sum(ad_sales) from last7)                as acos_7d,
            (select sum(ad_spend) / sum(net_sales) from last7)               as tacos_7d,
            (select sum(contribution_profit) / sum(net_sales) from last7)    as margin_7d,
            (select sum(orders) from last7)                                  as orders_7d
        """
    ).fetchone()
    as_of, sales_7d, sales_prev, acos, tacos, margin, orders = k
    wow = (sales_7d - sales_prev) / sales_prev

    inv = con.execute(
        "select sku, title, fulfillable_qty, days_of_cover, days_until_restock, status "
        "from mart_inventory_health where status in ('OUT OF STOCK', 'Stockout risk')"
    ).fetchall()
    camp = con.execute(
        "select campaign_name, acos, breakeven_acos, ad_profit_30d, recommendation "
        "from mart_campaign_actions where recommendation like 'Cut%' order by ad_profit_30d limit 5"
    ).fetchall()
    scale = con.execute(
        "select count(*) from mart_campaign_actions where recommendation like 'Scale%'"
    ).fetchone()[0]

    lines = [
        f"**Data through {as_of}** · last pipeline run {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
        "",
        "| Last 7 days | Value |",
        "|---|---|",
        f"| Net sales | {money(sales_7d)} ({'+' if wow >= 0 else ''}{wow * 100:.1f}% vs prior 7 days) |",
        f"| Orders | {orders:,} |",
        f"| ACoS (ad spend / ad sales) | {pct(acos)} |",
        f"| TACoS (ad spend / total sales) | {pct(tacos)} |",
        f"| Contribution margin after ads | {pct(margin)} |",
        "",
        "**Inventory alerts**",
        "",
    ]
    if inv:
        lines += ["| SKU | Product | On hand | Days of cover | Days until restock | Status |", "|---|---|---|---|---|---|"]
        lines += [
            f"| {s} | {t} | {q:,} | {'-' if c is None else c} | {r} | {st} |" for s, t, q, c, r, st in inv
        ]
    else:
        lines.append("No SKUs at risk of stocking out.")
    lines += ["", f"**Campaigns losing money (last 30 days)** · {scale} campaign(s) flagged to scale up", ""]
    if camp:
        lines += ["| Campaign | ACoS | Break-even ACoS | Ad profit | Action |", "|---|---|---|---|---|"]
        lines += [f"| {c} | {pct(a)} | {pct(b)} | {money(p)} | {r} |" for c, a, b, p, r in camp]
    else:
        lines.append("No campaigns above break-even ACoS.")
    return "\n".join(lines)


def update_readme(block: str) -> None:
    start, end = "<!-- KPI:START -->", "<!-- KPI:END -->"
    text = README.read_text()
    if start not in text or end not in text:
        print("  README markers not found; skipping README update")
        return
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    README.write_text(f"{head}{start}\n{block}\n{end}{tail}")


def append_run_log(con: duckdb.DuckDBPyConnection, checks: list[dict]) -> None:
    as_of, order_lines = con.execute("select max(order_date), count(*) from stg_orders").fetchone()
    raw_rows = con.execute(
        f"select count(*) from read_csv('{RAW_DIR.as_posix()}/orders/*.csv', all_varchar = true)"
    ).fetchone()[0]
    row = pd.DataFrame(
        [
            {
                "run_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "data_through": as_of,
                "raw_order_rows": raw_rows,
                "order_lines_after_dedup": order_lines,
                "duplicates_removed": raw_rows - order_lines,
                "checks_passed": sum(c["status"] == "PASS" for c in checks),
                "checks_warned": sum(c["status"] == "WARN" for c in checks),
                "checks_failed": sum(c["status"] == "FAIL" for c in checks),
            }
        ]
    )
    row.to_csv(RUN_LOG, mode="a", header=not RUN_LOG.exists(), index=False)


def main() -> int:
    con = duckdb.connect()  # in-memory warehouse, rebuilt from raw files each run
    # Load the product catalog from a visible seed file (dbt-style seed)
    con.register("seed_products", pd.read_csv(ROOT / "data" / "seeds" / "products.csv"))

    print("Building models...")
    run_sql_models(con)

    print("Running data quality checks...")
    checks = run_checks(con)
    if any(c["status"] == "FAIL" for c in checks):
        print("Data quality checks failed; marts were not published.")
        return 1

    print("Publishing marts...")
    MARTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    for table in MART_TABLES:
        con.execute(f"copy {table} to '{(MARTS_DIR / f'{table}.csv').as_posix()}' (header, delimiter ',')")

    chart = render_chart(con.execute("select * from mart_daily_kpis order by date").df())
    print(f"  chart -> {chart.relative_to(ROOT)}")
    update_readme(build_kpi_markdown(con))
    append_run_log(con, checks)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
