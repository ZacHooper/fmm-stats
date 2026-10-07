-- Each staff member's spells on a team's books, keyed (person_id,
-- first_seen_date): the team, its club, the role ('manager' or 'staff') and
-- the snapshot bounds (int.staff_spells for the rules). The save gives no
-- staff contract, so a spell's dates are the snapshots that show it.
select
    person_id,
    first_seen_date,
    team_tid,
    club_tid,
    role,
    manager_candidates,
    last_seen_date,
    ended_by_date,
    ended_by_date is null as is_current
from {{ ref('int_staff_spells') }}
