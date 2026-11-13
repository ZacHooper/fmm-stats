-- Our squad on each snapshot, keyed (snapshot_date, person_id): who the squad
-- arrays list as ours and who is out on loan, with each one's status
-- (int.our_squad), and for a loan either way its agreed end and the share of
-- his wage the borrowing club pays (fact_loan_spell, from the loan pool).
with career as (
    select * from {{ ref('stg_career') }}
)

select
    squad.snapshot_date,
    squad.person_id,
    squad.status,
    squad.is_loan_in,
    squad.loaned_to_club_tid,
    loans.parent_club_tid as loan_parent_club_tid,
    loans.start_date as loan_start_date,
    loans.end_date as loan_end_date,
    loans.wage_pct as loan_wage_pct
from {{ ref('int_our_squad') }} as squad
cross join career
inner join {{ ref('stg_snapshots') }} as snapshots
    on squad.snapshot_date = snapshots.snapshot_date
left join {{ ref('fact_loan_spell') }} as loans
    on
        squad.person_id = loans.person_id
        and snapshots.season = loans.season
        and loans.borrowing_club_tid = case
            when squad.is_loan_in then career.managed_club_tid
            else squad.loaned_to_club_tid
        end
        and (squad.is_loan_in or squad.loaned_to_club_tid is not null)
