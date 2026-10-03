-- The events of our own matches, in order (event_index): minute, stoppage
-- time, period, type, the player and the side the event counts for (an own
-- goal counts for the other side; player_team_tid is the scorer's own). The
-- match's date and teams are on dim_match (match_id).
select
    match_id,
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
