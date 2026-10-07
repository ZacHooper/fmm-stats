-- The dated moves the development chart marks, one row per move, keyed
-- (person_id, move_type, move_date):
--   transfer  a move between clubs (fact_transfer) with a known date: the date
--             his record says he joined; fee_type 'fee' for a fee paid, 'free'
--             for a free move, 'none' for a graduation from a youth side,
--             'unknown' where the history's fee code is not understood
--   internal  a move between our first team and reserve side: the first
--             snapshot on the new team
-- from_club_tid and to_club_tid are clubs for a transfer (from_club_tid NULL
-- for a free agent's signing), our teams for an internal move.
with career as (
    select * from {{ ref('stg_career') }}
),

ours as (
    select teams.team_tid
    from {{ ref('dim_team') }} as teams
    inner join career
        on teams.club_tid = career.managed_club_tid
),

transfers as (
    select
        person_id,
        move_date,
        from_club_tid,
        to_club_tid,
        'transfer' as move_type,
        case transfer_type
            when 'permanent' then 'fee'
            when 'free' then 'free'
            when 'graduation' then 'none'
            else 'unknown'
        end as fee_type,
        fee_gbp
    from {{ ref('fact_transfer') }}
    where move_date is not null
),

internal as (
    select
        steps.person_id,
        steps.snapshot_date as move_date,
        steps.previous_team_tid as from_club_tid,
        steps.team_tid as to_club_tid,
        'internal' as move_type,
        'none' as fee_type,
        cast(null as bigint) as fee_gbp
    from (
        select
            person_id,
            snapshot_date,
            team_tid,
            lag(team_tid) over (
                partition by person_id order by snapshot_date
            ) as previous_team_tid
        from {{ ref('fact_player_snapshot') }}
    ) as steps
    where
        steps.team_tid in (select ours.team_tid from ours)
        and steps.previous_team_tid in (select ours.team_tid from ours)
        and steps.team_tid <> steps.previous_team_tid
)

select * from transfers
union all
select * from internal
