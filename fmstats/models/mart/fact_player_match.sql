-- One row per (match_id, player_tid). Minute intervals (a sub's minutes
-- included, a sending-off ending them; stoppage time not counted) and his
-- stats. Matches carry player lines only where dim_match.has_detail; the
-- match's date and teams are on dim_match (match_id).
-- rating_adj is the rating restated for the position played
-- (int_player_match_ratings); is_player_of_match is the game's own pick, one
-- player per match.
select
    matches.match_id,
    matches.player_tid,
    matches.person_id,
    matches.team_tid,
    matches.opponent_tid,
    matches.pos_order,
    matches.position,
    ratings.role,
    matches.started,
    matches.appeared,
    matches.is_player_of_match,
    matches.sub_on_minute,
    matches.sub_off_minute,
    matches.sent_off_minute,
    matches.minutes,
    matches.rating,
    ratings.rating_adj,
    matches.goals,
    matches.assists,
    matches.passes,
    matches.passes_completed,
    matches.key_passes,
    matches.tackles,
    matches.tackles_won,
    matches.interceptions,
    matches.headers,
    matches.headers_won,
    matches.crosses,
    matches.crosses_completed,
    matches.dribbles,
    matches.mistakes,
    matches.mistakes_to_goal,
    matches.shots,
    matches.shots_on_target,
    matches.condition,
    matches.yellows
from {{ ref('int_player_matches') }} as matches
left join {{ ref('int_player_match_ratings') }} as ratings
    on
        matches.match_id = ratings.match_id
        and matches.player_tid = ratings.player_tid
