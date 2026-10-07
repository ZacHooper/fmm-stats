-- Every team's squad on each snapshot, one row per player listed, with the
-- team's type and the club that owns it (int_teams). A player can be listed by
-- more than one team (a loanee is listed by both clubs for a while), so this
-- is the listing, not a verdict on where he plays.
select
    squads.snapshot_date,
    squads.team_tid,
    squads.player_tid,
    squads.slot,
    teams.team_type,
    coalesce(teams.club_tid, squads.team_tid) as club_tid
from {{ ref('stg_team_squads') }} as squads
left join {{ ref('int_teams') }} as teams
    on
        squads.snapshot_date = teams.snapshot_date
        and squads.team_tid = teams.team_tid
