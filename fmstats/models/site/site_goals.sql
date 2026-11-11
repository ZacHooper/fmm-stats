-- Each goal in the managed (senior) team's matches with detail, both sides',
-- keyed (match_id, event_index): the minute, the kind (goal, penalty or
-- own goal), the scorer (tid; for an own goal the player who put it in his
-- own net), the side it counts for and, on FMM27, the assister. The web app
-- pairs scorers with their assisters from it. A shoot-out kick is not a goal.
select
    matches.match_id,
    events.event_index,
    matches.season,
    matches.match_date,
    matches.competition,
    events.minute,
    events.added_minutes,
    events.event_type,
    events.player_tid as tid,
    events.person_id,
    events.team_tid,
    events.assist_tid,
    events.assist_person_id
from {{ ref('fact_match_event') }} as events
inner join {{ ref('site_matches') }} as matches
    on events.match_id = matches.match_id
inner join {{ ref('int_event_types') }} as event_kinds
    on events.event_type_code = event_kinds.code
where event_kinds.scores_for is not null
