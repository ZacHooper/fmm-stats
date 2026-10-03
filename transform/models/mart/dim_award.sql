-- The awards a player's entry in the save records, from var('awards'): the
-- World Best XI pool of a season (the 100 players the game picks that year's
-- eleven from; which eleven it picks is not stored) and the World Best XI
-- All-Time pool.
{% for award_id, name in var('awards').items() %}
select
    '{{ award_id }}' as award_id,
    '{{ name }}' as name
{% if not loop.last %}union all{% endif %}
{% endfor %}
