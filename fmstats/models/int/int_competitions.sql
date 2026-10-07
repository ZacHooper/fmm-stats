-- Each competition once: the values the save does not change between
-- snapshots, from the latest snapshot it appears in. Reputation changes and is
-- on int_competition_snapshots.
select
    cid,
    uid,
    name,
    short_name,
    code,
    type,
    type_id,
    nation_id,
    level,
    parent_cid,
    last_seen_date
from ({{ latest(ref('stg_competitions'), 'cid') }})
