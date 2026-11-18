-- Each team in the home nation's men's leagues on each snapshot, for the
-- Regions tab's club table: its name, region, league and tier, Elo rating and
-- facilities (fact_club_region_snapshot).
select
    clubs.snapshot_date,
    clubs.team_tid,
    teams.name,
    clubs.home_region_id,
    clubs.tier,
    clubs.is_scored,
    competition.name as league_name,
    clubs.elo,
    clubs.reputation,
    clubs.youth_facilities,
    clubs.training_facilities
from {{ ref('fact_club_region_snapshot') }} as clubs
inner join {{ ref('dim_team') }} as teams
    on clubs.team_tid = teams.team_tid
left join {{ ref('fact_team_snapshot') }} as team_snapshot
    on
        clubs.snapshot_date = team_snapshot.snapshot_date
        and clubs.team_tid = team_snapshot.team_tid
left join {{ ref('dim_competition') }} as competition
    on team_snapshot.league_cid = competition.cid
