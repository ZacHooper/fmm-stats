-- Our squad's value and wage bill on each snapshot (site.squad), over the
-- players we own (not those on loan to us, but those out on loan): their
-- value, the model's estimate where the save holds none (n_value_est of
-- them), and their wages. wage_paid_gbp is the bill we actually pay: our own
-- players' wages less the share a borrowing club pays on a loan out, plus the
-- share we pay on a loan in (loan_wage_pct, from the loan pool; a loan the pool
-- does not hold counts as no change to who pays).
select
    squad.snapshot_date,
    snapshots.season,
    count(*) filter (where not squad.is_loan_in) as n_owned,
    count(*) filter (where squad.is_loan_in) as n_loan_in,
    sum(players.value) filter (where not squad.is_loan_in) as value_gbp,
    count(*) filter (
        where not squad.is_loan_in and players.value_is_estimated
    ) as n_value_est,
    sum(players.wage_gbp) filter (where not squad.is_loan_in) as wage_gbp,
    sum(
        case
            when squad.is_loan_in
                then players.wage_gbp * coalesce(squad.loan_wage_pct, 0) / 100
            when squad.loaned_to_club_tid is not null
                then
                    players.wage_gbp
                    * (100 - coalesce(squad.loan_wage_pct, 0))
                    / 100
            else players.wage_gbp
        end
    ) as wage_paid_gbp
from {{ ref('site_squad') }} as squad
inner join {{ ref('stg_snapshots') }} as snapshots
    on squad.snapshot_date = snapshots.snapshot_date
left join {{ ref('fact_player_snapshot') }} as players
    on
        squad.snapshot_date = players.snapshot_date
        and squad.person_id = players.person_id
group by squad.snapshot_date, snapshots.season
