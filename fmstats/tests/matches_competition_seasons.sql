-- fact_player_competition_season sums fact_player_match exactly: for every
-- campaign (the match date's season by the career's rollover day), team and
-- competition, the same appearances, starts, minutes, goals, assists and
-- sendings-off, placeholder players with no person record included.
with career as (
    select * from {{ ref('stg_career') }}
),

from_matches as (
    select
        {{ season_of('matches.match_date') }} as season,
        player_lines.team_tid,
        matches.cid,
        count(*) filter (where player_lines.appeared) as apps,
        count(*) filter (where player_lines.started) as games_started,
        sum(player_lines.minutes) as minutes_played,
        sum(player_lines.goals) as goals,
        sum(player_lines.assists) as assists,
        count(player_lines.sent_off_minute) as sendings_off
    from {{ ref('fact_player_match') }} as player_lines
    inner join {{ ref('dim_match') }} as matches
        on player_lines.match_id = matches.match_id
    cross join career
    group by all
),

from_seasons as (
    select
        season,
        team_tid,
        cid,
        sum(apps) as apps,
        sum(games_started) as games_started,
        sum(minutes) as minutes_played,
        sum(goals) as goals,
        sum(assists) as assists,
        sum(sendings_off) as sendings_off
    from {{ ref('fact_player_competition_season') }}
    group by season, team_tid, cid
)

select
    coalesce(from_matches.season, from_seasons.season) as season,
    coalesce(from_matches.team_tid, from_seasons.team_tid) as team_tid,
    coalesce(from_matches.cid, from_seasons.cid) as cid,
    from_matches.apps as match_apps,
    from_seasons.apps as season_apps,
    from_matches.goals as match_goals,
    from_seasons.goals as season_goals
from from_matches
full outer join from_seasons
    on
        from_matches.season = from_seasons.season
        and from_matches.team_tid = from_seasons.team_tid
        and from_matches.cid = from_seasons.cid
where
    from_matches.apps is distinct from from_seasons.apps
    or from_matches.games_started is distinct from from_seasons.games_started
    or from_matches.minutes_played is distinct from from_seasons.minutes_played
    or from_matches.goals is distinct from from_seasons.goals
    or from_matches.assists is distinct from from_seasons.assists
    or from_matches.sendings_off is distinct from from_seasons.sendings_off
