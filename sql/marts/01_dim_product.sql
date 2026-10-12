-- Product dimension with unit economics.
-- breakeven_acos: the ACoS at which ad-driven sales make zero profit.
create or replace table dim_product as
select
    sku,
    asin,
    title,
    category,
    cast(list_price as decimal(10, 2))                       as list_price,
    cast(unit_cost as decimal(10, 2))                        as unit_cost,
    cast(fba_fee as decimal(10, 2))                          as fba_fee,
    cast(round(list_price * {referral_fee_rate}, 2) as decimal(10, 2)) as referral_fee,
    cast(round(list_price - unit_cost - fba_fee - list_price * {referral_fee_rate}, 2) as decimal(10, 2))
                                                             as unit_margin_before_ads,
    round((list_price - unit_cost - fba_fee - list_price * {referral_fee_rate}) / list_price, 4)
                                                             as breakeven_acos,
    lead_time_days
from seed_products;
