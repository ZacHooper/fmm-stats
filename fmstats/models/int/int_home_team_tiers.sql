-- Each team in a men's league of the career's home nation (the nation whose
-- league the managed club plays in) on each snapshot, with that league's tier
-- (1 the top flight; parallel divisions share one). Reserve and women's
-- leagues are left out.
with home as (
    select club.league_nation_id as nation_id
    from {{ ref('int_club_snapshots') }} as club
    inner join {{ ref('stg_career') }} as career
        on club.club_tid = career.managed_club_tid
    where club.is_current
)

select
    team.snapshot_date,
    team.team_tid,
    team.club_tid,
    team.league_cid,
    competition.nation_id,
    competition.level + 1 as tier
from {{ ref('int_team_snapshots') }} as team
inner join {{ ref('int_competitions') }} as competition
    on team.league_cid = competition.cid
inner join home
    on competition.nation_id = home.nation_id
where
    competition.type = 'league'
    and not competition.is_women
