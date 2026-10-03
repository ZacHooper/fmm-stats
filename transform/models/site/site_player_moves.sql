-- The dated moves the development chart marks, one row per move:
--   transfer  a move between clubs (fact_transfer) with a known date: the date
--             his record says he joined; fee_type 'fee' for a fee paid, 'free'
--             for a free move, 'none' for a graduation from a youth side,
--             'unknown' where the history's fee code is not understood
--   internal  a move between our first team and reserve side: the first
--             snapshot on the new team
-- from_club_tid and to_club_tid are clubs for a transfer, our teams for an
-- internal move.
with career as (
    select * from {{ ref('stg_career') }}
),

ours as (
    select team_tid
    from {{ ref('dim_team') }}
    inner join career
        on dim_team.club_tid = career.managed_club_tid
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
        person_id,
        snapshot_date as move_date,
        previous_team_tid as from_club_tid,
        team_tid as to_club_tid,
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
        team_tid in (select team_tid from ours)
        and previous_team_tid in (select team_tid from ours)
        and team_tid <> previous_team_tid
)

select * from transfers
union all
select * from internal
