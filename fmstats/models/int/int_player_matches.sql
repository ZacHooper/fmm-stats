-- Each player's line in our own matches, both sides, once: keyed
-- (match_id, player_tid), from the snapshot
-- int_our_matches reads the match from. started is a place in the XI
-- (pos_order up to var('starters')), appeared a start or a substitution on.
-- minutes runs from kick-off, or the minute he came on, to the minute he went
-- off, was sent off or the match ended: var('match_minutes'), extra time
-- included where the match had it (decided_by 'ET' or 'pens'). The save marks
-- a dismissal only with its event (int_event_types.ends_appearance), and
-- stoppage time is not counted. position is a starter's full-time place in our XI,
-- NULL for the opposition and for substitutes. person_id is NULL for a player
-- the snapshot holds no person record for.
{%- set minutes = var('match_minutes') %}

with lines as (
    select
        ours.match_id,
        stats.*
    from {{ ref('int_our_matches') }} as ours
    inner join {{ ref('stg_match_player_stats') }} as stats
        on
            ours.source_snapshot_date = stats.snapshot_date
            and ours.anchor = stats.anchor
),

sent_off as (
    select
        events.match_id,
        events.player_tid,
        min(events.minute) as sent_off_minute
    from {{ ref('int_match_events') }} as events
    inner join {{ ref('int_event_types') }} as event_kinds
        on events.event_type_code = event_kinds.code
    where event_kinds.ends_appearance
    group by all
),

placed as (
    select
        lines.*,
        sent_off.sent_off_minute,
        lines.pos_order <= {{ var('starters') }} as started,
        lines.pos_order <= {{ var('starters') }}
        or lines.sub_on_minute is not null as appeared,
        case
            when matches.decided_by in ('ET', 'pens')
                then {{ minutes['extra_time'] }}
            else {{ minutes['regulation'] }}
        end as match_minutes
    from lines
    left join sent_off
        on
            lines.match_id = sent_off.match_id
            and lines.player_tid = sent_off.player_tid
    left join {{ ref('int_matches') }} as matches
        on lines.match_id = matches.match_id
)

select
    placed.match_id,
    placed.player_tid,
    persons.person_id,
    placed.team_tid,
    placed.opponent_tid,
    placed.pos_order,
    placed.position,
    placed.started,
    placed.appeared,
    placed.sub_on_minute,
    placed.sub_off_minute,
    placed.sent_off_minute,
    case
        when placed.appeared
            then least(
                coalesce(placed.sub_off_minute, placed.match_minutes),
                coalesce(placed.sent_off_minute, placed.match_minutes)
            ) - coalesce(placed.sub_on_minute, 0)
        else 0
    end as minutes,
    placed.rating,
    placed.goals,
    placed.assists,
    placed.passes,
    placed.passes_completed,
    placed.key_passes,
    placed.tackles,
    placed.tackles_won,
    placed.interceptions,
    placed.headers,
    placed.headers_won,
    placed.crosses,
    placed.crosses_completed,
    placed.dribbles,
    placed.mistakes,
    placed.mistakes_to_goal,
    placed.shots,
    placed.shots_on_target,
    placed.condition,
    placed.yellows,
    placed.snapshot_date as source_snapshot_date
from placed
left join {{ ref('int_person_snapshots') }} as persons
    on
        placed.snapshot_date = persons.snapshot_date
        and placed.player_tid = persons.tid
