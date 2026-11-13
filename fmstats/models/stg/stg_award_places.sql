-- Every stored edition of every award, its 1st to 3rd places, per snapshot:
-- the person's tid and name ids as they were when he placed (a tid is a slot
-- a newgen can take later), his club then and the score (votes on a voted
-- award, goals on a Top Goalscorer). An unfilled place is all NULL. The
-- edition's date is 1 January of its year on an annual award, and the 1st of
-- the month after the one it is for on a monthly award.
select
    cast(phase as date) as snapshot_date,
    award_id,
    cast(edition_date as date) as edition_date,
    place,
    cast(nullif(person_tid, {{ var('no_id32') }}) as integer) as person_tid,
    nullif(first_name_id, {{ var('no_id32') }}) as first_name_id,
    nullif(last_name_id, {{ var('no_id32') }}) as last_name_id,
    nullif(common_name_id, {{ var('no_id32') }}) as common_name_id,
    cast(nullif(club_tid, {{ var('no_id32') }}) as integer) as club_tid,
    case
        when person_tid != {{ var('no_id32') }} then score
    end as score
from {{ source('raw', 'award_places') }}
