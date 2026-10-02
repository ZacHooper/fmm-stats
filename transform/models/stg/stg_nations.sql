-- The nation table, one row per nation per snapshot. Each id field reads NULL
-- where the record holds var('no_id16') ("none").
{%- set no_id = var('no_id16') %}

select
    cast(phase as date) as snapshot_date,
    id as nation_id,
    uid,
    name,
    nationality,
    code,
    nullif(continent_id, {{ no_id }}) as continent_id,
    nullif(capital_city_id, {{ no_id }}) as capital_city_id,
    nullif(national_stadium_id, {{ no_id }}) as national_stadium_id,
    rival_nation_id,
    is_ranked,
    world_ranking,
    ranking_points
from {{ source('raw', 'nations') }}
