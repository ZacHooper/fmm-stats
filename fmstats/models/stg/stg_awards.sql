-- The game's awards, one row per award per snapshot: its name as the award
-- screens list it ('Top Goalscorer') and in full ('Premier League Top
-- Goalscorer'), and what it is for: a competition (cid), a nation, a
-- continent, NULL where it is wider. last_date is the day its latest edition
-- was decided, NULL when it has never been (stored as 1 Jan 1900).
select
    cast(phase as date) as snapshot_date,
    award_id,
    uid,
    name as short_name,
    long_name as name,
    nullif(continent_id, {{ var('no_id16') }}) as continent_id,
    nullif(nation_id, {{ var('no_id16') }}) as nation_id,
    nullif(cid, {{ var('no_id16') }}) as cid,
    case
        when last_year > 1900
            then make_date(last_year, 1, 1) + cast(last_day as integer)
    end as last_date
from {{ source('raw', 'awards') }}
