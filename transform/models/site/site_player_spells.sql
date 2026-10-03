-- Where each player was, as dated spells, for the development chart: one row
-- per spell, keyed (person_id, spell_type, from_date).
--   at_club   a run of his consecutive snapshots on one team's books (the team
--             his record names, so first team and reserves are two spells),
--             from the date his record says he joined, where that lies
--             between the run's first snapshot and the one before it, else
--             the first snapshot; to the run's last snapshot, NULL while it
--             runs on the newest
--   loan_out  a loan of ours with dates (fact_loan_spell: Player Progress),
--             club_tid the borrowing club
--   loan_in   a loan to us: the snapshots our squad lists him (NULL to while
--             it does on the newest), club_tid the parent club
--   injured   an injury (fact_injury_spell), no club
with career as (
    select * from {{ ref('stg_career') }}
),

snapshots as (
    select
        snapshot_date,
        lag(snapshot_date) over (order by snapshot_date) as previous_date,
        snapshot_date = max(snapshot_date) over () as is_latest
    from {{ ref('stg_snapshots') }}
),

steps as (
    select
        players.person_id,
        players.snapshot_date,
        players.team_tid,
        players.joined_date,
        snapshots.previous_date,
        snapshots.is_latest,
        (
            lag(players.team_tid) over w is distinct from players.team_tid
            or lag(players.snapshot_date) over w
            is distinct from snapshots.previous_date
        ) as starts_run
    from {{ ref('fact_player_snapshot') }} as players
    inner join snapshots
        on players.snapshot_date = snapshots.snapshot_date
    window w as (partition by players.person_id order by players.snapshot_date)
),

runs as (
    select
        *,
        sum(case when starts_run then 1 else 0 end) over (
            partition by person_id order by snapshot_date
        ) as run
    from steps
),

at_club as (
    select
        person_id,
        'at_club' as spell_type,
        any_value(team_tid) as club_tid,
        coalesce(
            arg_min(
                case
                    when
                        joined_date <= snapshot_date
                        and (
                            previous_date is null or joined_date > previous_date
                        )
                        then joined_date
                end,
                snapshot_date
            ),
            min(snapshot_date)
        ) as from_date,
        case when not bool_or(is_latest) then max(snapshot_date) end as to_date
    from runs
    where team_tid is not null
    group by person_id, run
),

loans_out as (
    select
        loans.person_id,
        'loan_out' as spell_type,
        loans.borrowing_club_tid as club_tid,
        loans.start_date as from_date,
        loans.end_date as to_date
    from {{ ref('fact_loan_spell') }} as loans
    inner join career
        on loans.parent_club_tid = career.managed_club_tid
    where loans.start_date is not null
),

loans_in as (
    select
        loans.person_id,
        'loan_in' as spell_type,
        loans.parent_club_tid as club_tid,
        loans.first_seen_date as from_date,
        case
            when
                loans.last_seen_date
                < (
                    select max(latest.snapshot_date) as latest_date
                    from snapshots as latest
                )
                then loans.last_seen_date
        end as to_date
    from {{ ref('fact_loan_spell') }} as loans
    inner join career
        on loans.borrowing_club_tid = career.managed_club_tid
    where loans.first_seen_date is not null
),

injuries as (
    select
        person_id,
        'injured' as spell_type,
        cast(null as integer) as club_tid,
        start_date as from_date,
        end_date as to_date
    from {{ ref('fact_injury_spell') }}
)

select * from at_club
union all
select * from loans_out
union all
select * from loans_in
union all
select * from injuries
