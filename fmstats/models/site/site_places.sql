-- Where each team plays on each snapshot, keyed (snapshot_date, team_tid): the
-- stadium its record names, the stadium's capacity on the
-- snapshot and its city's coordinates, with the team's league, the league's
-- nation and tier (site.clubs, site.leagues).
select
    clubs.snapshot_date,
    clubs.team_tid,
    clubs.name as club,
    clubs.team_type,
    clubs.league_cid,
    clubs.league_name,
    clubs.nation,
    clubs.is_listed,
    leagues.tier,
    stadiums.name as stadium,
    stadiums.capacity,
    cities.latitude,
    cities.longitude
from {{ ref('site_clubs') }} as clubs
left join {{ ref('site_leagues') }} as leagues
    on
        clubs.snapshot_date = leagues.snapshot_date
        and clubs.league_cid = leagues.cid
left join {{ ref('fact_team_snapshot') }} as teams
    on
        clubs.snapshot_date = teams.snapshot_date
        and clubs.team_tid = teams.team_tid
left join {{ ref('fact_stadium_snapshot') }} as stadiums
    on
        clubs.snapshot_date = stadiums.snapshot_date
        and teams.stadium_id = stadiums.stadium_id
left join {{ ref('dim_stadium') }} as stadium_dims
    on stadiums.stadium_id = stadium_dims.stadium_id
left join {{ ref('dim_city') }} as cities
    on stadium_dims.city_id = cities.city_id
