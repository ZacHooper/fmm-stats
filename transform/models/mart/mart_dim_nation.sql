-- Each nation as a place: names, capital, national stadium, rival and the
-- languages it speaks, as its latest snapshot gives them.
select
    nation_id,
    name,
    nationality,
    code,
    continent_id,
    capital_city_id,
    national_stadium_id,
    rival_nation_id,
    languages,
    last_seen_date
from {{ ref('int_nations') }}
