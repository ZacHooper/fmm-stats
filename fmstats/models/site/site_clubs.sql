-- Every team on every snapshot, keyed (snapshot_date, team_tid): its name,
-- club, league (int.team_leagues: the newest its record named), the league's
-- nation, its reputation and how many players its record holds, and its
-- club's home shirt colours (dim_club.shirt_colours: main, then second).
--
-- is_listed: a team worth naming in the web app's club pickers, one with a
-- rated player, one we played that season, or one on a career line of a
-- player with two lines or more. The rest are the save's empty slots: national
-- sides, reserve sides with no squad, clubs no player passes through.
with snapshots as (
    select * from {{ ref('stg_snapshots') }}
),

players as (
    select
        snapshot_date,
        team_tid,
        count(*) as squad_size,
        count(*) filter (where has_attributes) as rated_players
    from {{ ref('fact_player_snapshot') }}
    where team_tid is not null
    group by snapshot_date, team_tid
),

played as (
    select distinct
        snapshots.snapshot_date,
        unnest([matches.home_team_tid, matches.away_team_tid]) as team_tid
    from {{ ref('int_our_matches') }} as matches
    cross join {{ ref('stg_career') }} as career
    inner join snapshots
        on
            matches.match_date <= snapshots.snapshot_date
            and {{ season_of('matches.match_date') }} = snapshots.season
),

careers as (
    select distinct
        people.snapshot_date,
        career_lines.team_tid
    from {{ ref('fact_player_season') }} as career_lines
    inner join {{ ref('fact_player_snapshot') }} as people
        on career_lines.person_id = people.person_id
    inner join snapshots
        on people.snapshot_date = snapshots.snapshot_date
    where
        career_lines.season <= snapshots.season
        and career_lines.team_tid is not null
    qualify count(*) over (
        partition by people.snapshot_date, people.person_id
    ) > 1
)

select
    teams.snapshot_date,
    teams.team_tid,
    teams.club_tid,
    teams.name,
    teams.team_type,
    leagues.league_cid,
    competitions.name as league_name,
    nations.name as nation,
    team_snapshots.reputation,
    clubs.shirt_colours,
    coalesce(players.squad_size, 0) as squad_size,
    (
        coalesce(players.rated_players, 0) > 0
        or played.team_tid is not null
        or careers.team_tid is not null
    ) as is_listed
from {{ ref('int_teams') }} as teams
left join {{ ref('dim_club') }} as clubs
    on teams.club_tid = clubs.club_tid
left join {{ ref('fact_team_snapshot') }} as team_snapshots
    on
        teams.snapshot_date = team_snapshots.snapshot_date
        and teams.team_tid = team_snapshots.team_tid
left join {{ ref('int_team_leagues') }} as leagues
    on
        teams.snapshot_date = leagues.snapshot_date
        and teams.team_tid = leagues.team_tid
left join {{ ref('dim_competition') }} as competitions
    on leagues.league_cid = competitions.cid
left join {{ ref('dim_nation') }} as nations
    on competitions.nation_id = nations.nation_id
left join players
    on
        teams.snapshot_date = players.snapshot_date
        and teams.team_tid = players.team_tid
left join played
    on
        teams.snapshot_date = played.snapshot_date
        and teams.team_tid = played.team_tid
left join careers
    on
        teams.snapshot_date = careers.snapshot_date
        and teams.team_tid = careers.team_tid
