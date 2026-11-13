-- Every award the store knows: the game's awards (int.awards, by their id in
-- the save's awards table) and the World Best XI pools the scrapbook records
-- (var('awards')).
select
    cast(award_id as varchar) as award_id,
    name,
    short_name,
    award_type,
    period as award_period,
    cid,
    nation_id,
    continent_id
from {{ ref('int_awards') }}
{% for award_id, name in var('awards').items() %}
union all
select
    '{{ award_id }}' as award_id,
    '{{ name }}' as name,
    '{{ name }}' as short_name,
    'pool' as award_type,
    'season' as award_period,
    null as cid,
    null as nation_id,
    null as continent_id
{% endfor %}
