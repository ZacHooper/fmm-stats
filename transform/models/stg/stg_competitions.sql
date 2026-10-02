-- The competition table, every named slot per snapshot. type is the decoded
-- type_id ('type_<n>' where the code has no name yet). level is the 0-indexed
-- division tier, which puts parallel divisions on one tier.
select
    cast(phase as date) as snapshot_date,
    cid,
    uid,
    name,
    short as short_name,
    code,
    type,
    type_id,
    nation_id,
    reputation,
    level,
    parent_cid
from {{ source('raw', 'competitions') }}
