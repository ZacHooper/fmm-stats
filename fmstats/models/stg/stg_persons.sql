-- The person table, one record per person (players and staff) per snapshot:
-- identity, club, personality, and the two links. A player's attribute record
-- is the one with his `sid` (NULL for staff, stored var('no_sid')); a staff
-- member's staff record the one with his `id2` (NULL for players, stored
-- var('no_id32')). club_tid is NULL for a free agent (var('no_id16')).
select
    cast(phase as date) as snapshot_date,
    cast(tid as integer) as tid,
    uid,
    first_name_id,
    last_name_id,
    common_name_id,
    dob,
    nationality_id,
    second_nationality_id,
    ethnicity,
    type_flag,
    unknown_date,
    international_caps,
    international_goals,
    u21_caps,
    u21_goals,
    cast(nullif(club_tid, {{ var('no_id16') }}) as integer) as club_tid,
    joined_date,
    {% for column in var('personality') %}
    {{ column }},
    {% endfor %}
    nullif(sid, '{{ var('no_sid') }}') as sid,
    nullif(id2, {{ var('no_id32') }}) as id2
from {{ source('raw', 'person_records') }}
