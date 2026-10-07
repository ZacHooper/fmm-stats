-- Each nation as a place: names, capital, national stadium and rival. What
-- changes (ranking, coefficients, languages) is on fact_nation_snapshot.
select
    nation_id,
    name,
    nationality,
    code,
    continent_id,
    capital_city_id,
    national_stadium_id,
    rival_nation_id,
    last_seen_date
from {{ ref('int_nations') }}
