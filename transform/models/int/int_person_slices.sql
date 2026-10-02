-- (season, phase, tid) -> person_id, the join every fact table uses.
select
    season,
    phase,
    tid,
    {{ person_id() }} as person_id
from {{ ref('int_players') }}
