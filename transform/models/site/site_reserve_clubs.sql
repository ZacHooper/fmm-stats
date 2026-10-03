-- mart.reserve_clubs on the new layers: our teams other than the first team.
select teams.team_tid as club_tid
from {{ ref('dim_team') }} as teams
inner join {{ ref('stg_career') }} as career
    on
        teams.club_tid = career.managed_club_tid
        and teams.team_tid <> career.managed_club_tid
