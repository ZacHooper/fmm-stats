-- Every loan in the loan pool as stored, one row per player on loan: the club
-- he is on loan at, the agreed start and end, the share of his wage that club
-- pays (0-100) and the option flag. The pool holds a loan from its start day
-- until it ends; the parent club is the player's own record's club.
select
    cast(phase as date) as snapshot_date,
    tid,
    slot,
    club_tid as borrowing_club_tid,
    start_date,
    end_date,
    wage_pct,
    option = 1 as has_option
from {{ source('raw', 'loans') }}
