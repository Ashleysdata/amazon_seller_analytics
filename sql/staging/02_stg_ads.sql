-- Staging: Sponsored Products advertised-product report
create or replace table stg_ads as
select
    cast("Date" as date)                         as report_date,
    "Campaign Name"                              as campaign_name,
    split_part("Campaign Name", ' / ', 3)        as targeting_type,
    "Ad Group Name"                              as ad_group_name,
    "Advertised SKU"                             as sku,
    upper("Advertised ASIN")                     as asin,
    cast("Impressions" as integer)               as impressions,
    cast("Clicks" as integer)                    as clicks,
    cast("Spend" as decimal(12, 2))              as spend,
    cast("7 Day Total Orders (#)" as integer)    as ad_orders,
    cast("7 Day Total Sales" as decimal(12, 2))  as ad_sales
from read_csv('{raw_dir}/ads/*.csv', header = true, all_varchar = true);
