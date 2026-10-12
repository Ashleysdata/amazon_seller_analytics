-- Last-30-day campaign performance with a bid recommendation.
-- A campaign is judged against its product's break-even ACoS:
--   ACoS above break-even  -> every ad sale loses money
--   ACoS well below it     -> room to raise bids and win more volume
create or replace table mart_campaign_actions as
with window_bounds as (
    select max(report_date) as end_date, max(report_date) - interval 29 day as start_date
    from stg_ads
),

perf as (
    select
        a.campaign_name,
        a.sku,
        a.targeting_type,
        sum(a.impressions)  as impressions,
        sum(a.clicks)       as clicks,
        sum(a.spend)        as spend,
        sum(a.ad_orders)    as ad_orders,
        sum(a.ad_sales)     as ad_sales
    from stg_ads a, window_bounds w
    where a.report_date between w.start_date and w.end_date
    group by all
)

select
    p.campaign_name,
    p.sku,
    d.title,
    p.targeting_type,
    p.impressions,
    p.clicks,
    round(p.spend, 2)                                     as spend_30d,
    round(p.ad_sales, 2)                                  as ad_sales_30d,
    round(p.clicks / nullif(p.impressions, 0), 4)         as ctr,
    round(p.ad_orders / nullif(p.clicks, 0), 4)           as conversion_rate,
    round(p.spend / nullif(p.ad_sales, 0), 4)             as acos,
    d.breakeven_acos,
    -- Profit from ad-attributed units after product costs and ad spend
    round(p.ad_orders * d.unit_margin_before_ads - p.spend, 2) as ad_profit_30d,
    case
        when p.clicks < 100                                 then 'Wait: not enough data'
        when p.spend / nullif(p.ad_sales, 0) > d.breakeven_acos      then 'Cut bids: losing money'
        when p.spend / nullif(p.ad_sales, 0) < d.breakeven_acos * 0.6 then 'Scale: raise bids'
        else 'Hold'
    end                                                   as recommendation
from perf p
join dim_product d using (sku)
order by ad_profit_30d;
