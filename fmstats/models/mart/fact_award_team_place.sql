-- Every team of the period the store has seen (Team of the Week, Team of the
-- Year, Dream Team ...), keyed (award_id, edition_date, team_place): its 11
-- players, each with his club then and the rating that earned the place.
-- int.award_team_places has the rules.
select
    cast(award_id as varchar) as award_id,
    season,
    edition_date,
    slot as team_place,
    person_id,
    person_tid,
    name as entry_name,
    club_tid,
    rating as selection_rating
from {{ ref('int_award_team_places') }}
