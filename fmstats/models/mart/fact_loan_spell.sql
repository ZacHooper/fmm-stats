-- Every loan, keyed (person_id, season, borrowing_club_tid): the parent club,
-- the borrowing team, the agreed start and end and the share of his wage the
-- borrowing club pays (from the loan pool), the snapshots listing him there
-- (int.loan_spells for the sources and rules). A loan is not a transfer and
-- makes no contract.
select
    person_id,
    season,
    borrowing_club_tid,
    borrowing_team_tid,
    parent_club_tid,
    start_date,
    end_date,
    is_dated_by_pool,
    ended_early_by_date,
    wage_pct,
    has_option,
    first_seen_date,
    last_seen_date,
    has_line
from {{ ref('int_loan_spells') }}
order by person_id, season
