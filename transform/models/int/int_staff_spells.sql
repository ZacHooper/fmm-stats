-- Each staff member's spells at a team, rebuilt from the snapshots: one row
-- per run of his consecutive staff snapshots on the same team's books in the
-- same role, keyed (person_id, first_seen_date). The save gives no staff
-- contract, so a spell has only snapshot bounds: first_seen_date and
-- last_seen_date, and ended_by_date, the store's next snapshot (NULL while he
-- is there on the newest).
--
-- role: the save names no job. A club's staff array lists its coaches and not
-- its manager, so the manager is the staff member on a team's books whom its
-- staff array does not list, the highest home reputation where more than one
-- is not listed (manager_candidates counts them); everyone else is 'staff'.
-- A team whose own record the save does not hold has no array, so its staff
-- read 'staff'. club_tid is the club that owns the team.
with snapshots as (
    select
        snapshot_date,
        lead(snapshot_date) over (order by snapshot_date) as next_date
    from {{ ref('stg_snapshots') }}
),

unlisted as (
    select
        staff.snapshot_date,
        staff.tid,
        staff.club_tid as team_tid,
        row_number() over (
            partition by staff.snapshot_date, staff.club_tid
            order by staff.home_reputation desc nulls last, staff.tid asc
        ) as reputation_rank,
        count(*) over (
            partition by staff.snapshot_date, staff.club_tid
        ) as manager_candidates
    from {{ ref('int_staff_snapshots') }} as staff
    inner join {{ ref('stg_club_details') }} as details
        on
            staff.snapshot_date = details.snapshot_date
            and staff.club_tid = details.tid
    left join {{ ref('stg_club_staff') }} as listed
        on
            staff.snapshot_date = listed.snapshot_date
            and staff.club_tid = listed.club_tid
            and staff.tid = listed.staff_tid
    where listed.staff_tid is null
),

roles as (
    select
        staff.person_id,
        staff.snapshot_date,
        staff.club_tid as team_tid,
        coalesce(teams.club_tid, staff.club_tid) as club_tid,
        case
            when unlisted.reputation_rank = 1 then 'manager' else 'staff'
        end as role,
        case
            when unlisted.reputation_rank = 1
                then unlisted.manager_candidates
        end as manager_candidates
    from {{ ref('int_staff_snapshots') }} as staff
    left join {{ ref('int_teams') }} as teams
        on
            staff.snapshot_date = teams.snapshot_date
            and staff.club_tid = teams.team_tid
    left join unlisted
        on
            staff.snapshot_date = unlisted.snapshot_date
            and staff.tid = unlisted.tid
    where staff.club_tid is not null
),

-- every staff snapshot of each person, on a team or not, so that a snapshot
-- without a team ends the run
everyone as (
    select
        staff.person_id,
        staff.snapshot_date,
        roles.team_tid,
        roles.club_tid,
        roles.role,
        roles.manager_candidates
    from {{ ref('int_staff_snapshots') }} as staff
    left join roles
        on
            staff.person_id = roles.person_id
            and staff.snapshot_date = roles.snapshot_date
),

lagged as (
    select
        *,
        lag(team_tid) over w as previous_team_tid,
        lag(role) over w as previous_role
    from everyone
    window w as (partition by person_id order by snapshot_date)
),

numbered as (
    select
        *,
        sum(
            case
                when
                    (previous_team_tid is distinct from team_tid)
                    or (previous_role is distinct from role)
                    then 1
                else 0
            end
        ) over (
            partition by person_id order by snapshot_date
        ) as spell_number
    from lagged
),

spells as (
    select
        person_id,
        min(snapshot_date) as first_seen_date,
        any_value(team_tid) as team_tid,
        any_value(club_tid) as club_tid,
        any_value(role) as role,
        max(manager_candidates) as manager_candidates,
        max(snapshot_date) as last_seen_date
    from numbered
    where team_tid is not null
    group by person_id, spell_number
)

select
    spells.*,
    snapshots.next_date as ended_by_date
from spells
inner join snapshots
    on spells.last_seen_date = snapshots.snapshot_date
