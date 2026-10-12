-- Inventory health as of the latest snapshot.
-- Sales velocity is measured on in-stock days only; counting out-of-stock days
-- as zero would understate demand and hide the real stockout risk.
create or replace table mart_inventory_health as
with latest as (
    select max(date) as as_of from fct_daily_sku
),

velocity as (
    select
        f.sku,
        avg(f.units) filter (where not f.is_out_of_stock) as avg_daily_units_28d
    from fct_daily_sku f, latest l
    where f.date > l.as_of - interval 28 day
    group by f.sku
),

history as (
    select
        sku,
        count(*) filter (where is_out_of_stock)             as days_out_of_stock,
        avg(units) filter (where not is_out_of_stock)       as avg_units_in_stock_days
    from fct_daily_sku
    group by sku
),

current_stock as (
    select s.*
    from stg_inventory s, latest l
    where s.snapshot_date = l.as_of
)

select
    c.snapshot_date                                         as as_of_date,
    c.sku,
    p.title,
    c.fulfillable_qty,
    c.inbound_qty,
    c.inbound_eta,
    round(v.avg_daily_units_28d, 1)                         as avg_daily_units_28d,
    round(c.fulfillable_qty / nullif(v.avg_daily_units_28d, 0), 1) as days_of_cover,
    coalesce(c.inbound_eta - c.snapshot_date, p.lead_time_days)    as days_until_restock,
    h.days_out_of_stock                                     as days_out_of_stock_all_time,
    -- Lost sales estimate: out-of-stock days x normal in-stock velocity x price
    round(h.days_out_of_stock * h.avg_units_in_stock_days * p.list_price, 0) as est_lost_revenue_all_time,
    case
        when c.fulfillable_qty = 0 then 'OUT OF STOCK'
        when c.fulfillable_qty / nullif(v.avg_daily_units_28d, 0)
             < coalesce(c.inbound_eta - c.snapshot_date, p.lead_time_days) then 'Stockout risk'
        when c.fulfillable_qty / nullif(v.avg_daily_units_28d, 0) > 90 then 'Overstock'
        else 'Healthy'
    end                                                     as status
from current_stock c
join dim_product p using (sku)
left join velocity v using (sku)
left join history h using (sku)
order by days_of_cover nulls first;
