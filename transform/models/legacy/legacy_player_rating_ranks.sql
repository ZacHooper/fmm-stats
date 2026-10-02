-- The old v_player_rating_ranks shape: each rank with the player's name, the
-- club he is listed under and that club's league.
select
    players.season,
    players.phase,
    ranks.method,
    ranks.role,
    ranks.tid,
    ranks.rating,
    players.name,
    players.club,
    players.club_tid,
    details.league_cid,
    ranks.pctile,
    ranks.rank_overall
from {{ ref('int_player_rating_ranks') }} as ranks
{{ join_snapshots('ranks') }}
inner join {{ ref('legacy_players') }} as players
    on
        snapshots.season = players.season
        and strftime(ranks.snapshot_date, '%Y-%m-%d') = players.phase
        and ranks.tid = players.tid
left join {{ ref('stg_club_details') }} as details
    on
        ranks.snapshot_date = details.snapshot_date
        and players.club_tid = details.tid
