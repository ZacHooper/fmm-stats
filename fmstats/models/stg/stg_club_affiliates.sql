-- Each club's affiliations, one row per link as the club's record lists it.
-- A link names both clubs (club1_tid, club2_tid), so it appears under each.
-- Dates are as stored, day of the year and year.
select
    cast(phase as date) as snapshot_date,
    club_tid,
    seq,
    club1_tid,
    club2_tid,
    start_day,
    start_year,
    end_day,
    end_year
from {{ source('raw', 'club_affiliates') }}
