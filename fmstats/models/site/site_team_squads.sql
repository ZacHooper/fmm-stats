-- Every team's current squad, keyed (team_tid, person_id): the squad arrays on
-- the latest snapshot (mart.squad_membership), never a player's own club
-- field, which a lapsed loan can leave pointing at a club he has left. tid is
-- the player's id in the web app's player files.
select
    squads.team_tid,
    squads.person_id,
    persons.tid,
    squads.is_loan_in
from {{ ref('mart_squad_membership') }} as squads
inner join {{ ref('dim_person') }} as persons
    on squads.person_id = persons.person_id
where squads.is_current
