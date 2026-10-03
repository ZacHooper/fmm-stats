-- mart.our_clubs on the new layers: every team of the club the career
-- manages (its first team, its reserve side and any b team).
select teams.team_tid as club_tid
from {{ ref('dim_team') }} as teams
inner join {{ ref('stg_career') }} as career
    on teams.club_tid = career.managed_club_tid
