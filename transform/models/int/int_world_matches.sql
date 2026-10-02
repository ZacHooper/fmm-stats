-- Every match in the world fixture list once: a match is (match_date,
-- home_team_tid, away_team_tid), and its row is the latest snapshot holding it.
-- home_goals_90 / away_goals_90 are the score after 90 minutes; home_goals /
-- away_goals the final score (after extra time where there was any).
-- decided_by is '90', 'ET' or 'pens', NULL for a match not yet played.
-- competition_season is the competition's own season label (the fixture's
-- season_year: 2025 for a 2025/26 league and for a calendar-year 2025 one).
select
    match_date,
    home_team_tid,
    away_team_tid,
    season_year as competition_season,
    stage_key,
    stage_index,
    round_index,
    round as matchday,
    seq_id,
    subr,
    home_goals as home_goals_90,
    away_goals as away_goals_90,
    coalesce(home_goals_aet, home_goals) as home_goals,
    coalesce(away_goals_aet, away_goals) as away_goals,
    home_pens,
    away_pens,
    case
        when home_goals is null then null
        when home_pens is not null then 'pens'
        when home_goals_aet is not null then 'ET'
        else '90'
    end as decided_by,
    snapshot_date as source_snapshot_date
from {{ ref('stg_world_fixtures') }}
qualify
    snapshot_date = max(snapshot_date) over (
        partition by match_date, home_team_tid, away_team_tid
    )
