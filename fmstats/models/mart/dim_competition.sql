-- Each competition: names, type, nation, division tier (tier_index, 0-indexed;
-- parallel divisions share a tier) and parent. Reputation changes and is on
-- fact_competition_snapshot.
select
    cid,
    uid,
    name,
    short_name,
    code,
    type,
    type_id,
    nation_id,
    level as tier_index,
    parent_cid,
    last_seen_date
from {{ ref('int_competitions') }}
