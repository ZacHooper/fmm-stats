-- Every match in the world, keyed (match_date, home_team_tid, away_team_tid):
-- its competition, stage and round where known (competition_source:
-- 'our_match' or 'team_league'; NULL for a stage the save does not let us
-- label), tie and leg, how it was decided, and has_detail for our own matches,
-- the only ones with events and player stats. The score is on fact_team_match;
-- score_display is for reading only.
select
    match_date,
    home_team_tid,
    away_team_tid,
    competition_season,
    cid,
    competition_source,
    stage_index,
    round_index,
    matchday,
    tie_id,
    leg,
    decided_by,
    score_display,
    has_detail,
    attendance
from {{ ref('int_matches') }}
