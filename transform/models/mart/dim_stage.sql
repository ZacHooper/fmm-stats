-- Each stage of a competition season: stage_format (knockout, league or group),
-- name, team count, groups, and whether it is the final stage. Rules change
-- between seasons, so a stage is keyed by its competition season.
select
    cid,
    competition_season,
    stage_index,
    stage_format,
    name,
    stage_code,
    stage_type,
    stage_teams,
    n_groups,
    is_final_stage
from {{ ref('int_stages') }}
