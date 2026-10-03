-- Every player contract, keyed (person_id, first_seen_date): the club, the date
-- it was signed (and started), its wage, expiry and team as first and last
-- seen, and how it ended (int.contracts for the rules). The end is a bound:
-- last_seen_date is the last snapshot it was in force, ended_by_date the next
-- one. A loan never makes a contract at the borrowing club.
select
    person_id,
    first_seen_date,
    club_tid,
    signed_date,
    stored_signed_date,
    first_team_tid,
    last_team_tid,
    first_wage_gbp,
    last_wage_gbp,
    first_expiry_date,
    last_expiry_date,
    last_seen_date,
    ended_by_date,
    end_reason,
    ended_by_date is null as is_current
from {{ ref('int_contracts') }}
