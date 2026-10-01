-- Each rating's percentile and rank among every player at that snapshot.
select
    ratings.season,
    ratings.phase,
    ratings.method,
    ratings.role,
    ratings.tid,
    ratings.rating,
    players.name,
    players.club,
    players.club_tid,
    -- the club record's league: league_id, unless it plays in another division
    case
        when
            details.other_division = 65535
            and details.league_id not in (0, 65535)
            then details.league_id
    end as league_cid,
    round(
        100 * percent_rank() over (
            partition by
                ratings.season, ratings.phase, ratings.method, ratings.role
            order by ratings.rating
        ),
        1
    ) as pctile,
    rank() over (
        partition by
            ratings.season, ratings.phase, ratings.method, ratings.role
        order by ratings.rating desc
    ) as rank_overall
from {{ ref('int_player_ratings') }} as ratings
inner join {{ ref('int_players') }} as players
    on
        ratings.season = players.season
        and ratings.phase = players.phase
        and ratings.tid = players.tid
left join {{ source('raw', 'club_details') }} as details
    on
        players.season = details.season
        and players.phase = details.phase
        and players.club_tid = details.tid
where not players.is_staff
