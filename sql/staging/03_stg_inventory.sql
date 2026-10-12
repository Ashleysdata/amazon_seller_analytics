-- Staging: end-of-day FBA inventory snapshots
create or replace table stg_inventory as
select
    cast(snapshot_date as date)                       as snapshot_date,
    sku,
    upper(asin)                                       as asin,
    cast(fulfillable_qty as integer)                  as fulfillable_qty,
    cast(inbound_qty as integer)                      as inbound_qty,
    cast(nullif(inbound_eta, '') as date)             as inbound_eta
from read_csv('{raw_dir}/inventory/*.csv', header = true, all_varchar = true);
