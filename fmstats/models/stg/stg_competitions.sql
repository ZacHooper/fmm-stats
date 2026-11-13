-- The competition table, every named slot per snapshot. type is the decoded
-- type_id ('type_<n>' where the code has no name yet). level is the 0-indexed
-- division tier, which puts parallel divisions on one tier. is_women is FMM27's
-- women's-competition flag; FMM22 stores no women's competitions, so false there.
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
    parent_cid,
    coalesce(is_women, false) as is_women
from {{ source('raw', 'competitions') }}
