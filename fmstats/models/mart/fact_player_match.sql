-- Each player's line in our own matches, both sides: the team he played for
-- that day, whether he started and appeared, his minutes (extra time
-- included, a sending-off ending them; stoppage time not counted) and his
-- stats. Matches carry player lines only where dim_match.has_detail; the
-- match's date and teams are on dim_match (match_id).
select
    match_id,
    player_tid,
    person_id,
    team_tid,
    opponent_tid,
    pos_order,
    position,
    started,
    appeared,
    sub_on_minute,
    sub_off_minute,
    sent_off_minute,
    minutes,
    rating,
    goals,
    assists,
    passes,
    passes_completed,
    key_passes,
    tackles,
    tackles_won,
    interceptions,
    headers,
    headers_won,
    crosses,
    crosses_completed,
    dribbles,
    mistakes,
    mistakes_to_goal,
    shots,
    shots_on_target,
    condition,
    yellows
from {{ ref('int_player_matches') }}
