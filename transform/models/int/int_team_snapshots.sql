-- Each team on each snapshot: what each side holds on its own record.
-- Reputation and status differ between a first team and its reserve side, so
-- they are the team's. A reserve side's record holds defaults, not values, for
-- the two facilities (training 10 and youth 0 on every reserve side, never
-- changing), so a reserve side has its club's; every other team, a b_team
-- included, has its own. youth_facilities is the record's academy byte.
-- last_league_position is the finish LAST season, in last_league_cid, not the
-- current standing. stadium_id is the team's own ground, else its club's (a
-- reserve side stores none). The record's att_avg / att_min / att_max are left
-- out: their names are borrowed and the values are not attendance
-- (docs/TODO.md).
{%- set reserve = var('team_types')[2] %}

select
    teams.snapshot_date,
    teams.team_tid,
    teams.club_tid,
    details.reputation,
    details.status,
    case
        when teams.team_type = '{{ reserve }}' then first_team.facilities
        else details.facilities
    end as training_facilities,
    case
        when teams.team_type = '{{ reserve }}' then first_team.academy
        else details.academy
    end as youth_facilities,
    details.league_cid,
    details.other_division_cid,
    details.last_league_cid,
    details.league_pos as last_league_position,
    coalesce(details.stadium_id, clubs.stadium_id) as stadium_id,
    details.squad_size,
    details.staff_size,
    teams.snapshot_date = max(teams.snapshot_date) over () as is_current
from {{ ref('int_teams') }} as teams
inner join {{ ref('stg_club_details') }} as details
    on
        teams.snapshot_date = details.snapshot_date
        and teams.team_tid = details.tid
left join {{ ref('int_club_snapshots') }} as clubs
    on
        teams.snapshot_date = clubs.snapshot_date
        and teams.club_tid = clubs.club_tid
left join {{ ref('stg_club_details') }} as first_team
    on
        teams.snapshot_date = first_team.snapshot_date
        and teams.club_tid = first_team.tid
