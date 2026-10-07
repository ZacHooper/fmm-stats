-- The teams of the club we manage, its first team first: the managed team
-- and its reserve side.
select
    teams.team_tid,
    teams.club_tid,
    teams.name,
    teams.is_first_team,
    teams.team_tid = career.managed_club_tid as is_managed
from {{ ref('dim_team') }} as teams
inner join {{ ref('stg_career') }} as career
    on teams.club_tid = career.managed_club_tid
