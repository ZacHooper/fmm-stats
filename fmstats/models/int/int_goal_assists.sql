-- Each assisted goal in our own matches, keyed (match_id, event_index) of the
-- goal event, with its assister. FMM27 writes an assist event after the goal
-- it made, in the same minute and for the scorer's side, before that side's
-- next goal (an unnamed event can sit between them), so a goal's assister is
-- the assist event whose latest earlier scoring event on its side is that
-- goal. FMM22 writes no assist events, so its goals have no row here.
with scoring as (
    select
        events.match_id,
        events.event_index,
        events.player_team_tid
    from {{ ref('int_match_events') }} as events
    inner join {{ ref('int_event_types') }} as event_kinds
        on events.event_type_code = event_kinds.code
    where event_kinds.scores_for = 'for'
),

assists as (
    select
        match_id,
        event_index,
        player_tid,
        person_id,
        player_team_tid
    from {{ ref('int_match_events') }}
    where event_type = 'assist'
)

select
    scoring.match_id,
    scoring.event_index,
    assists.player_tid as assist_tid,
    assists.person_id as assist_person_id
from assists
inner join scoring
    on
        assists.match_id = scoring.match_id
        and assists.player_team_tid = scoring.player_team_tid
        and assists.event_index > scoring.event_index
qualify
    scoring.event_index = max(scoring.event_index) over (
        partition by assists.match_id, assists.event_index
    )
