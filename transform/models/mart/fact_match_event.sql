-- The events of our own matches, in order (event_index): minute, stoppage
-- time, period, type, the player and the side the event counts for (an own
-- goal counts for the other side; player_team_tid is the scorer's own).
select
    match_date,
    home_team_tid,
    away_team_tid,
    event_index,
    minute,
    added_minutes,
    period,
    event_type_code,
    event_type,
    player_tid,
    person_id,
    player_team_tid,
    team_tid
from {{ ref('int_match_events') }}
