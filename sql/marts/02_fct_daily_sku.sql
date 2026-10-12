-- Grain: one row per SKU per day.
-- The inventory snapshot is the date spine, so days with zero sales still appear.
create or replace table fct_daily_sku as
with sales as (
    select
        order_date,
        sku,
        count(distinct order_id)  as orders,
        sum(quantity)             as units,
        sum(net_sales)            as net_sales
    from stg_orders
    where not is_cancelled
    group by all
),

ads as (
    select
        report_date,
        sku,
        sum(impressions)  as impressions,
        sum(clicks)       as clicks,
        sum(spend)        as ad_spend,
        sum(ad_sales)     as ad_sales,
        sum(ad_orders)    as ad_orders
    from stg_ads
    group by all
)

select
    i.snapshot_date                                   as date,
    i.sku,
    p.category,
    coalesce(s.orders, 0)                             as orders,
    coalesce(s.units, 0)                              as units,
    coalesce(s.net_sales, 0)                          as net_sales,
    coalesce(s.units, 0) * p.unit_cost                as cogs,
    coalesce(s.units, 0) * p.fba_fee
        + coalesce(s.net_sales, 0) * {referral_fee_rate} as amazon_fees,
    coalesce(a.impressions, 0)                        as impressions,
    coalesce(a.clicks, 0)                             as clicks,
    coalesce(a.ad_spend, 0)                           as ad_spend,
    coalesce(a.ad_sales, 0)                           as ad_sales,
    coalesce(a.ad_orders, 0)                          as ad_orders,
    i.fulfillable_qty                                 as ending_inventory,
    i.inbound_qty,
    i.fulfillable_qty = 0                             as is_out_of_stock
from stg_inventory i
join dim_product p using (sku)
left join sales s on s.order_date = i.snapshot_date and s.sku = i.sku
left join ads   a on a.report_date = i.snapshot_date and a.sku = i.sku;

-- Contribution profit after COGS, Amazon fees and advertising
alter table fct_daily_sku add column contribution_profit decimal(14, 2);
update fct_daily_sku
set contribution_profit = net_sales - cogs - amazon_fees - ad_spend;
