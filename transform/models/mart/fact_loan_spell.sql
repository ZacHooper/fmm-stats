-- Every loan, keyed (person_id, season, borrowing_club_tid): the parent club,
-- the borrowing team, the snapshots listing him there, and real start and end
-- dates for a loan out of the club we manage (int.loan_spells for the
-- sources and rules). A loan is not a transfer and makes no contract.
select
    person_id,
    season,
    borrowing_club_tid,
    borrowing_team_tid,
    parent_club_tid,
    start_date,
    end_date,
    first_seen_date,
    last_seen_date,
    has_line
from {{ ref('int_loan_spells') }}
