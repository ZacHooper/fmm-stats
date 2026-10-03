-- Our squad on each snapshot, keyed (snapshot_date, person_id): who the squad
-- arrays list as ours and who is out on loan, with each one's status
-- (int.our_squad).
select
    snapshot_date,
    person_id,
    status,
    is_loan_in,
    loaned_to_club_tid
from {{ ref('int_our_squad') }}
