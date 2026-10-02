-- Each competition's stage and round structure, from its rules member in the
-- save archive: one row per round, or per stage where it has no rounds.
-- stage_index and round_index are the numbers stg_world_fixtures carries; the
-- name ids resolve through stg_round_names.
select
    cast(phase as date) as snapshot_date,
    uid as competition_uid,
    stage_index,
    stage_code,
    stage_type,
    stage_teams,
    stage_name_id,
    n_groups,
    round_index,
    round_name_id,
    round_teams,
    legs
from {{ source('raw', 'competition_rounds') }}
