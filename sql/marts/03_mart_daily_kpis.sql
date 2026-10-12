-- Account-level daily KPIs for the dashboard.
--   ACoS  = ad spend / ad-attributed sales   (efficiency of ads themselves)
--   TACoS = ad spend / total sales           (how dependent the business is on ads)
create or replace table mart_daily_kpis as
with daily as (
    select
        date,
        sum(orders)               as orders,
        sum(units)                as units,
        sum(net_sales)            as net_sales,
        sum(ad_spend)             as ad_spend,
        sum(ad_sales)             as ad_sales,
        sum(contribution_profit)  as contribution_profit,
        count(*) filter (where is_out_of_stock) as skus_out_of_stock
    from fct_daily_sku
    group by date
)

select
    date,
    orders,
    units,
    round(net_sales, 2)                                       as net_sales,
    round(ad_spend, 2)                                        as ad_spend,
    round(ad_sales, 2)                                        as ad_sales,
    round(ad_spend / nullif(ad_sales, 0), 4)                  as acos,
    round(ad_spend / nullif(net_sales, 0), 4)                 as tacos,
    round(contribution_profit, 2)                             as contribution_profit,
    round(contribution_profit / nullif(net_sales, 0), 4)      as contribution_margin,
    skus_out_of_stock,
    round(avg(net_sales) over (order by date rows between 6 preceding and current row), 2)
                                                              as net_sales_7d_avg,
    round(sum(ad_spend) over w7 / nullif(sum(net_sales) over w7, 0), 4)
                                                              as tacos_7d
from daily
window w7 as (order by date rows between 6 preceding and current row)
order by date;
