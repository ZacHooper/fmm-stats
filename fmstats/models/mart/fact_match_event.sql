-- The events of our own matches, in order (event_index): minute, stoppage
-- time, period, type, the player and the side the event counts for (an own
-- goal counts for the other side; player_team_tid is the scorer's own). The
-- match's date and teams are on dim_match (match_id). A goal's assister is on
-- its own row (assist_tid, int_goal_assists): FMM27 only.
select
    events.match_id,
    events.event_index,
    events.minute,
    events.added_minutes,
    events.period,
    events.event_type_code,
    events.event_type,
    events.player_tid,
    events.person_id,
    events.player_team_tid,
    events.team_tid,
    assists.assist_tid,
    assists.assist_person_id
from {{ ref('int_match_events') }} as events
left join {{ ref('int_goal_assists') }} as assists
    on
        events.match_id = assists.match_id
        and events.event_index = assists.event_index
