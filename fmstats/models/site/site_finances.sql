-- Our squad's value and wage bill on each snapshot (site.squad), over the
-- players we own (not those on loan to us, but those out on loan): their
-- value, the model's estimate where the save holds none (n_value_estimated of
-- them), and their wages.
select
    squad.snapshot_date,
    snapshots.season,
    count(*) filter (where not squad.is_loan_in) as n_owned,
    count(*) filter (where squad.is_loan_in) as n_loan_in,
    sum(players.value_gbp) filter (where not squad.is_loan_in) as value_gbp,
    count(*) filter (
        where not squad.is_loan_in and players.is_value_estimated
    ) as n_value_estimated,
    sum(players.wage_gbp) filter (where not squad.is_loan_in) as wage_gbp
from {{ ref('site_squad') }} as squad
inner join {{ ref('stg_snapshots') }} as snapshots
    on squad.snapshot_date = snapshots.snapshot_date
left join {{ ref('fact_player_snapshot') }} as players
    on
        squad.snapshot_date = players.snapshot_date
        and squad.person_id = players.person_id
group by squad.snapshot_date, snapshots.season
