-- Staging: Seller Central "All Orders" report
-- Cleans the raw flat files: types, ASIN casing, price text -> numeric,
-- and removes duplicate rows that Seller Central exports occasionally repeat.
create or replace table stg_orders as
with raw as (
    select *
    from read_csv('{raw_dir}/orders/*.csv', header = true, all_varchar = true, filename = true)
),

typed as (
    select
        "amazon-order-id"                                        as order_id,
        cast("purchase-date" as timestamptz)                     as purchased_at,
        -- Kept in UTC for simplicity; Seller Central US reports use Pacific time
        cast(cast("purchase-date" as timestamptz) at time zone 'UTC' as date) as order_date,
        "order-status"                                           as order_status,
        "order-status" = 'Cancelled'                             as is_cancelled,
        sku,
        upper(asin)                                              as asin,
        cast(quantity as integer)                                as quantity,
        cast(replace("item-price", '$', '') as decimal(12, 2))   as gross_sales,
        cast("item-promotion-discount" as decimal(12, 2))        as promo_discount,
        "ship-state"                                             as ship_state,
        filename                                                 as source_file
    from raw
)

select
    * exclude (source_file),
    gross_sales - promo_discount as net_sales,
    source_file
from typed
qualify row_number() over (partition by order_id, sku order by source_file) = 1;
