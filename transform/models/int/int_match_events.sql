-- The events of our own matches once each, keyed (match_date, home_team_tid,
-- away_team_tid, event_index): a match's events come from the snapshot
-- int_our_matches reads the match from. period is the period the minute falls
-- in (var('match_periods')), and a shoot-out kick its own; stoppage time
-- (added_minutes) stays in the period it extends. player_team_tid is the
-- player's side, team_tid the side the event counts for: the player's,
-- except an own goal's (int_event_types.scores_for), which counts for the
-- other side.
-- person_id is NULL for a player the snapshot holds no person record for.
{%- set periods = var('match_periods') %}

with events as (
    select
        ours.match_date,
        ours.home_team_tid,
        ours.away_team_tid,
        events.seq,
        events.minute,
        events.added,
        events.type_byte,
        events.event_type,
        events.player_tid,
        events.snapshot_date,
        case events.side
            when 'home' then ours.home_team_tid
            when 'away' then ours.away_team_tid
        end as player_team_tid,
        case events.side
            when 'home' then ours.away_team_tid
            when 'away' then ours.home_team_tid
        end as other_team_tid
    from {{ ref('int_our_matches') }} as ours
    inner join {{ ref('stg_match_events') }} as events
        on
            ours.source_snapshot_date = events.snapshot_date
            and ours.anchor = events.anchor
)

select
    events.match_date,
    events.home_team_tid,
    events.away_team_tid,
    events.seq as event_index,
    events.minute,
    events.added as added_minutes,
    case
        when event_kinds.is_shootout then '{{ var("shootout_period") }}'
        {% for last_minute, period in periods %}
        when events.minute <= {{ last_minute }} then '{{ period }}'
        {% endfor %}
    end as period,
    events.type_byte as event_type_code,
    events.event_type,
    events.player_tid,
    persons.person_id,
    events.player_team_tid,
    case
        when event_kinds.scores_for = 'against' then events.other_team_tid
        else events.player_team_tid
    end as team_tid
from events
inner join {{ ref('int_event_types') }} as event_kinds
    on events.type_byte = event_kinds.code
left join {{ ref('int_person_snapshots') }} as persons
    on
        events.snapshot_date = persons.snapshot_date
        and events.player_tid = persons.tid
