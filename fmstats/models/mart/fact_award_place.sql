-- Every edition of every award the store has seen, keyed (award_id,
-- edition_date, place): the 1st to 3rd placed, with his club then and the
-- score. int.award_places has the rules.
select
    cast(award_id as varchar) as award_id,
    season,
    edition_date,
    place,
    person_id,
    person_tid,
    name as entry_name,
    club_tid,
    score
from {{ ref('int_award_places') }}
