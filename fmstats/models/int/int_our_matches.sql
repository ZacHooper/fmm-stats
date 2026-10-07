-- Our own matches once each: the match table is emptied at the rollover and
-- grows through a season, so a match's row is the latest snapshot holding it.
-- cid is the competition the match table names; match_id is the same key as
-- int_world_matches'. formation is the managed side's (is_home: the home
-- side); the team stats are each side's.
select
    {{ match_id('match_date', 'home_team_tid', 'away_team_tid') }} as match_id,
    match_date,
    home_team_tid,
    away_team_tid,
    anchor,
    cid,
    competition,
    is_home,
    attendance,
    score_home,
    score_away,
    formation,
    player_of_match,
    {% for side in ['home', 'away'] %}
    {% for stat in var('team_match_stats') %}
    {{ side }}_{{ stat }},
    {% endfor %}
    {% endfor %}
    snapshot_date as source_snapshot_date
from {{ ref('stg_matches') }}
qualify
    snapshot_date = max(snapshot_date) over (
        partition by match_date, home_team_tid, away_team_tid
    )
