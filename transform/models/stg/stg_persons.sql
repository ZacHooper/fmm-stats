-- Every person's own record (players and staff share it), one row per person
-- per snapshot. club_tid is NULL for a free agent (the save's var('no_id16')).
-- The *_src columns are the record's attribute bytes as stored; the attribute
-- decode (int.player_attribute_estimates) reads them.
select
    cast(phase as date) as snapshot_date,
    tid,
    first_name_id,
    last_name_id,
    common_name_id,
    is_staff,
    nullif(club_tid, {{ var('no_id16') }}) as club_tid,
    dob,
    nationality_id,
    second_nationality_id,
    ethnicity,
    has_attributes,
    is_gk = 1 as is_goalkeeper,
    ca,
    pa,
    reputation,
    current_reputation,
    world_reputation,
    foot_left,
    foot_right,
    international_retired,
    squad_number,
    preferred_squad_number,
    height_cm,
    weight_kg,
    {% for column in var('hidden_attributes') %}
    {{ column }},
    {% endfor %}
    {% for column in var('attribute_columns').values()
        if column not in var('hidden_attributes') %}
    {{ column }},
    {% endfor %}
    {% for column in var('personality') %}
    {{ column }},
    {% endfor %}
    international_caps,
    international_goals,
    u21_caps,
    u21_goals,
    joined_date
from {{ source('raw', 'players_raw') }}
