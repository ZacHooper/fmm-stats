-- Each team: the side that plays, with the club that owns it. team_type is
-- first, reserve, b_team (a second side in the senior pyramid), national or
-- national_u21; is_first_team marks the team that owns its club. club_type is
-- the save's own code.
select
    team_tid,
    club_tid,
    name,
    team_type,
    is_first_team,
    club_type,
    last_seen_date
from {{ ref('int_team_list') }}
