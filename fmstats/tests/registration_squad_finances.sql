-- Our squad's value and wage bill (site_finances) covers every snapshot, and
-- every player we own has a value and a wage on it; the save states the value
-- of nearly all of them, so the model's estimates stand in for under a
-- quarter of the owned player-snapshots. One row per snapshot without a
-- finances row, one per owned player without a value or a wage, and one if
-- the estimated share reaches a quarter.
with owned as (
    select
        squad.snapshot_date,
        squad.person_id,
        players.value,
        players.wage_gbp
    from {{ ref('site_squad') }} as squad
    left join {{ ref('fact_player_snapshot') }} as players
        on
            squad.snapshot_date = players.snapshot_date
            and squad.person_id = players.person_id
    where not squad.is_loan_in
)

select
    'no finances row' as check_name,
    snapshots.snapshot_date,
    null as person_id
from {{ ref('stg_snapshots') }} as snapshots
left join {{ ref('site_finances') }} as finances
    on snapshots.snapshot_date = finances.snapshot_date
where finances.snapshot_date is null
union all
select
    case
        when owned.value is null then 'owned player unvalued'
        else 'owned player unwaged'
    end as check_name,
    owned.snapshot_date,
    owned.person_id
from owned
where owned.value is null or owned.wage_gbp is null
union all
select
    'value mostly estimated' as check_name,
    null as snapshot_date,
    null as person_id
from {{ ref('site_finances') }}
having sum(n_value_est) >= 0.25 * sum(n_owned)
