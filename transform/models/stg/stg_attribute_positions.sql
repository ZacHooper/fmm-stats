-- Each attribute record's position familiarities, one row per position it
-- rates above 1 (the record's `positions`, unnested).
with keyed as (
    select
        cast(phase as date) as snapshot_date,
        sid,
        positions,
        unnest(json_keys(positions)) as position
    from {{ source('raw', 'attribute_records') }}
)

select
    snapshot_date,
    sid,
    position,
    cast(json_extract(positions, '$."' || position || '"') as integer)
        as familiarity
from keyed
