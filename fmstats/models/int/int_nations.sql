-- Each nation once, as a place: the values the save does not change between
-- snapshots, from the latest snapshot it appears in. What changes (ranking,
-- coefficients, the languages spoken) is on int_nation_snapshots.
select
    nation_id,
    uid,
    name,
    nationality,
    code,
    continent_id,
    capital_city_id,
    national_stadium_id,
    rival_nation_id,
    last_seen_date
from ({{ latest(ref('stg_nations'), 'nation_id') }})
