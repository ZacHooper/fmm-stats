-- Each player's line in our own matches, both sides, once: keyed
-- (match_id, player_tid), from the snapshot
-- int_our_matches reads the match from. started is a place in the XI
-- (pos_order up to var('starters')), appeared a start or a substitution on.
-- minutes runs from kick-off, or the minute he came on, to the minute he went
-- off, was sent off or the match ended: var('match_minutes'), extra time
-- included where the match had it (decided_by 'ET' or 'pens'), and stoppage
-- time not counted. sent_off_minute is the dismissal event's minute
-- (int_event_types.ends_appearance), which minutes uses; dismissal_minute is
-- the player line's own record of a sending-off, which also marks a
-- second-yellow dismissal that raises no event. position is a starter's
-- full-time place in his side's XI, NULL for substitutes. is_player_of_match
-- is the game's own Player of the Match (int_our_matches.player_of_match).
-- person_id is NULL for a player the snapshot holds no person record for.
-- xg and goals_conceded are FMM27's, NULL on an FMM22 match, and so are
-- clear_cut_chances (the clear-cut-chance events naming him) and
-- clear_cut_scored (those followed by his own goal in the same minute).
{%- set minutes = var('match_minutes') %}

with lines as (
    select
        ours.match_id,
        ours.player_of_match as player_of_match_tid,
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

chances as (
    select
        chances.match_id,
        chances.player_tid,
        count(distinct chances.event_index) as clear_cut_chances,
        count(
            distinct case
                when goals.event_index is not null then chances.event_index
            end
        ) as clear_cut_scored
    from {{ ref('int_match_events') }} as chances
    left join {{ ref('int_match_events') }} as goals
        on
            chances.match_id = goals.match_id
            and chances.player_tid = goals.player_tid
            and chances.minute = goals.minute
            and chances.event_index < goals.event_index
            and goals.event_type_code in (
                select event_kinds.code
                from {{ ref('int_event_types') }} as event_kinds
                where event_kinds.scores_for = 'for'
            )
    where chances.event_type = 'clear_cut_chance'
    group by chances.match_id, chances.player_tid
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
    coalesce(
        placed.player_tid = placed.player_of_match_tid, false
    ) as is_player_of_match,
    placed.sub_on_minute,
    placed.sub_off_minute,
    placed.sent_off_minute,
    placed.dismissal_minute,
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
    placed.xg,
    placed.goals_conceded,
    case
        when snapshots.save_format = 'fmm27'
            then coalesce(chances.clear_cut_chances, 0)
    end as clear_cut_chances,
    case
        when snapshots.save_format = 'fmm27'
            then coalesce(chances.clear_cut_scored, 0)
    end as clear_cut_scored,
    placed.snapshot_date as source_snapshot_date
from placed
inner join {{ ref('stg_snapshots') }} as snapshots
    on placed.snapshot_date = snapshots.snapshot_date
left join chances
    on
        placed.match_id = chances.match_id
        and placed.player_tid = chances.player_tid
left join {{ ref('int_person_snapshots') }} as persons
    on
        placed.snapshot_date = persons.snapshot_date
        and placed.player_tid = persons.tid
