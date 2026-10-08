-- A match event about a player in that match's lineup belongs to the side he
-- was fielded for (fact_player_match.team_tid), whatever club holds him at
-- any snapshot. A sent-off player's minutes end at his red card: the minute
-- he came on (0 for a starter) plus his minutes is never past it.
with red_cards as (
    select
        match_id,
        player_tid,
        min(minute) as red_card_minute
    from {{ ref('fact_match_event') }}
    where event_type = 'red_card'
    group by match_id, player_tid
)

select
    'event side differs from the lineup' as "check",
    events.match_id,
    events.player_tid,
    events.event_index as detail
from {{ ref('fact_match_event') }} as events
inner join {{ ref('fact_player_match') }} as player_lines
    on
        events.match_id = player_lines.match_id
        and events.player_tid = player_lines.player_tid
where events.player_team_tid is distinct from player_lines.team_tid
union all
select
    'minutes after a red card' as "check",
    player_lines.match_id,
    player_lines.player_tid,
    red_cards.red_card_minute as detail
from red_cards
inner join {{ ref('fact_player_match') }} as player_lines
    on
        red_cards.match_id = player_lines.match_id
        and red_cards.player_tid = player_lines.player_tid
where
    coalesce(player_lines.sub_on_minute, 0) + player_lines.minutes
    > red_cards.red_card_minute
