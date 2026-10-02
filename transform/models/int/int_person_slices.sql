SELECT season, phase, tid, {{ person_id() }} AS person_id FROM {{ ref('int_players') }}
