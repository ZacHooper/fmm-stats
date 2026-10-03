-- Each player's season in each competition he played in for each team, in
-- our own matches (both sides), keyed (season, player_tid, team_tid, cid):
-- summed from int.player_matches. season is the campaign the match was played
-- in (the season of the snapshot it was read from; the match table is emptied
-- at the rollover). avg_rating is over the matches he appeared in. person_id
-- is NULL for a placeholder player with no person record (reserve matches
-- fill out a side with them). A mid-season transfer gives a row per team;
-- friendlies are a competition like any other (dim_competition.type).
select
    snapshots.season,
    played.player_tid,
    played.team_tid,
    ours.cid,
    any_value(played.person_id) as person_id,
    count(*) filter (where played.appeared) as apps,
    count(*) filter (where played.started) as games_started,
    sum(played.minutes) as minutes,
    round(avg(played.rating) filter (where played.appeared), 2) as avg_rating,
    sum(played.goals) as goals,
    sum(played.assists) as assists,
    sum(played.key_passes) as key_passes,
    sum(played.passes) as passes,
    sum(played.passes_completed) as passes_completed,
    sum(played.tackles) as tackles,
    sum(played.tackles_won) as tackles_won,
    sum(played.interceptions) as interceptions,
    sum(played.headers) as headers,
    sum(played.headers_won) as headers_won,
    sum(played.crosses) as crosses,
    sum(played.crosses_completed) as crosses_completed,
    sum(played.shots) as shots,
    sum(played.shots_on_target) as shots_on_target,
    sum(played.dribbles) as dribbles,
    sum(played.mistakes) as mistakes,
    sum(played.mistakes_to_goal) as mistakes_to_goal,
    sum(played.yellows) as yellows,
    count(played.sent_off_minute) as sendings_off
from {{ ref('int_player_matches') }} as played
inner join {{ ref('int_our_matches') }} as ours
    on played.match_id = ours.match_id
inner join {{ ref('stg_snapshots') }} as snapshots
    on ours.source_snapshot_date = snapshots.snapshot_date
group by snapshots.season, played.player_tid, played.team_tid, ours.cid
