-- Every player contract, rebuilt from the snapshots: one row per contract,
-- keyed (person_id, first_seen_date). The save holds only each player's
-- current contract (stg_contracts.is_current), so a contract is a run of a
-- person's consecutive player snapshots whose current contract has the same
-- stored start date at the same club. A contract is written once and
-- replaced, never edited, so its start date is its identity: measured on the
-- gate stores, a contract whose start date is unchanged keeps it through
-- changes of wage and of team within the club (a move to the reserves), and a
-- new start date always lies between the two snapshots that bound it.
--
-- start_date is the stored start date where it is no later than the first
-- snapshot holding the contract; the save's day-one database holds start dates
-- up to eight months ahead on contracts already in force (and joined dates as
-- far ahead), which are not when those contracts began, so they read NULL.
-- stored_start_date keeps the stored value either way.
--
-- A free agent (no club) holds no contract, whatever the grid's slot says.
--
-- Wage, expiry and team are read on the first and the last snapshot holding
-- the contract: measured, 225 of 3,893 contracts seen twice or more change
-- wage under one start date, 3 change expiry and 544 team. The squad status
-- on the training row changes under one start date on 1,995 of them, so it
-- is not a contract term and stays on the player snapshot.
--
-- last_seen_date is the last snapshot the contract was in force, ended_by_date
-- the store's next snapshot (when it was replaced or gone; NULL while it is
-- in force on the newest snapshot). The real end lies between the two; the
-- next contract's start_date, where it lies between them, is the exact end.
-- end_reason is read from the person on ended_by_date:
--   renewed      a new contract at the same club
--   transferred  a contract at another club
--   expired      no contract (a free agent), the expiry already passed
--   released     no contract, the expiry not yet reached
--   retired      no player record (retired, or turned to coaching)
with snapshots as (
    select
        snapshot_date,
        lead(snapshot_date) over (order by snapshot_date) as next_date
    from {{ ref('stg_snapshots') }}
),

-- each player snapshot, with his current contract where he holds one
held as (
    select
        people.person_id,
        people.snapshot_date,
        coalesce(teams.club_tid, person.club_tid) as club_tid,
        person.club_tid as team_tid,
        contracts.start_date,
        contracts.expiry,
        contracts.wage_units
    from {{ ref('int_person_snapshots') }} as people
    inner join {{ ref('stg_persons') }} as person
        on
            people.snapshot_date = person.snapshot_date
            and people.tid = person.tid
    left join {{ ref('int_teams') }} as teams
        on
            person.snapshot_date = teams.snapshot_date
            and person.club_tid = teams.team_tid
    left join {{ ref('stg_contracts') }} as contracts
        on
            person.snapshot_date = contracts.snapshot_date
            and person.tid = contracts.tid
            and contracts.is_current
            and person.club_tid is not null
    where not people.is_staff
),

-- a new contract starts where the start date or club differs from the
-- person's previous snapshot, or he held none there
lagged as (
    select
        *,
        lag(start_date) over w as previous_start_date,
        lag(club_tid) over w as previous_club_tid
    from held
    window w as (partition by person_id order by snapshot_date)
),

marked as (
    select
        *,
        case
            when
                (previous_start_date is distinct from start_date)
                or (previous_club_tid is distinct from club_tid)
                then 1
            else 0
        end as starts_contract
    from lagged
),

numbered as (
    select
        *,
        sum(starts_contract) over (
            partition by person_id order by snapshot_date
        ) as contract_number
    from marked
),

contracts as (
    select
        person_id,
        contract_number,
        any_value(club_tid) as club_tid,
        any_value(start_date) as stored_start_date,
        min(snapshot_date) as first_seen_date,
        max(snapshot_date) as last_seen_date,
        arg_min_null(team_tid, snapshot_date) as first_team_tid,
        arg_max_null(team_tid, snapshot_date) as last_team_tid,
        arg_min_null(wage_units, snapshot_date) as first_wage_units,
        arg_max_null(wage_units, snapshot_date) as last_wage_units,
        arg_min_null(expiry, snapshot_date) as first_expiry_date,
        arg_max_null(expiry, snapshot_date) as last_expiry_date
    from numbered
    where start_date is not null
    group by person_id, contract_number
),

-- the person on the snapshot after each contract's last
succeeding as (
    select
        contracts.person_id,
        contracts.contract_number,
        snapshots.next_date as ended_by_date,
        next_held.person_id is not null as is_player,
        next_held.start_date is not null as has_contract,
        next_held.club_tid as next_club_tid
    from contracts
    inner join snapshots
        on contracts.last_seen_date = snapshots.snapshot_date
    left join held as next_held
        on
            contracts.person_id = next_held.person_id
            and snapshots.next_date = next_held.snapshot_date
)

select
    contracts.person_id,
    contracts.first_seen_date,
    contracts.club_tid,
    case
        when contracts.stored_start_date <= contracts.first_seen_date
            then contracts.stored_start_date
    end as start_date,
    contracts.stored_start_date,
    contracts.first_team_tid,
    contracts.last_team_tid,
    cast(contracts.first_wage_units as bigint)
    * {{ var('wage_gbp_per_unit') }} as first_wage_gbp,
    cast(contracts.last_wage_units as bigint)
    * {{ var('wage_gbp_per_unit') }} as last_wage_gbp,
    contracts.first_expiry_date,
    contracts.last_expiry_date,
    contracts.last_seen_date,
    succeeding.ended_by_date,
    case
        when succeeding.ended_by_date is null then null
        when not succeeding.is_player then 'retired'
        when
            succeeding.has_contract
            and succeeding.next_club_tid = contracts.club_tid
            then 'renewed'
        when succeeding.has_contract then 'transferred'
        when contracts.last_expiry_date < succeeding.ended_by_date
            then 'expired'
        else 'released'
    end as end_reason
from contracts
inner join succeeding
    on
        contracts.person_id = succeeding.person_id
        and contracts.contract_number = succeeding.contract_number
