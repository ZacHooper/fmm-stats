-- int_team_leagues resolves a team's league as at each snapshot: on a
-- snapshot whose own record names a league, that is the league, never one the
-- team was named in on a later snapshot. One row per team and snapshot where
-- the two differ.
select
    leagues.snapshot_date,
    leagues.team_tid,
    details.league_cid as named_league_cid,
    leagues.league_cid as resolved_league_cid
from {{ ref('int_team_leagues') }} as leagues
inner join {{ ref('stg_club_details') }} as details
    on
        leagues.snapshot_date = details.snapshot_date
        and leagues.team_tid = details.tid
where
    details.league_cid is not null
    and leagues.league_cid is distinct from details.league_cid
