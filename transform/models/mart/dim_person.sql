-- Every person in any snapshot, keyed person_id ('<tid>-<dob>': the game hands
-- a retired person's tid to a newgen, so tid alone would join two careers):
-- his name (the latest), date of birth, and the club and season of the oldest
-- career-history line any snapshot holds for him (origin_*; NULL for a person
-- who was never a player). That line is his first only where no snapshot had
-- yet dropped any (int.player_career_lines). Everything that changes is on
-- the snapshot facts.
with origins as (
    select
        person_id,
        club_tid as origin_club_tid,
        season as origin_season
    from {{ ref('int_player_career_lines') }}
    where line_index = 0
)

select
    persons.person_id,
    persons.tid,
    persons.dob,
    persons.name,
    origins.origin_club_tid,
    origins.origin_season,
    persons.first_seen as first_seen_date,
    persons.last_seen as last_seen_date
from {{ ref('int_persons') }} as persons
left join origins
    on persons.person_id = origins.person_id
