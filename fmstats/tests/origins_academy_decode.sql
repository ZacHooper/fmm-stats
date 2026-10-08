-- A club's academy (youth side) has no record of its own: its tid is the u16
-- complement of one of the club's teams, var('youth_tid_base') minus that
-- team's tid, and a player who came out of it has that club as his origin.
-- The decode holds only while the two id spaces never meet, so:
--   sentinel          the 0xFFFF "no origin" tid is never a team or an origin
--   collision         no two teams' tids are each other's complements, so a
--                     tid is a team or an academy, never both
--   not complement    an academy origin's club owns the team its tid is the
--                     complement of
--   not resolved      an academy origin's club is not the academy tid itself
--   no club           an academy origin's club is a club the save holds
--   no academies      somebody came out of an academy at all
-- One row per offending tid or person.
{% set base = var('youth_tid_base') %}
with people as (
    select
        person_id,
        origin_team_tid,
        origin_club_tid,
        origin_youth_team_tid
    from {{ ref('dim_person') }}
)

select
    'sentinel' as check_name,
    team_clubs.team_tid as tid,
    null as person_id
from {{ ref('int_team_clubs') }} as team_clubs
where team_clubs.team_tid = {{ base }}
union all
select
    'sentinel' as check_name,
    {{ base }} as tid,
    people.person_id
from people
where
    {{ base }} in (
        people.origin_team_tid,
        people.origin_club_tid,
        people.origin_youth_team_tid
    )
union all
select
    'collision' as check_name,
    teams.team_tid as tid,
    null as person_id
from {{ ref('dim_team') }} as teams
inner join {{ ref('dim_team') }} as complements
    on teams.team_tid = {{ base }} - complements.team_tid
union all
select
    'not complement' as check_name,
    people.origin_youth_team_tid as tid,
    people.person_id
from people
left join {{ ref('dim_team') }} as parents
    on {{ base }} - people.origin_youth_team_tid = parents.team_tid
where
    people.origin_youth_team_tid is not null
    and parents.club_tid is distinct from people.origin_club_tid
union all
select
    'not resolved' as check_name,
    people.origin_youth_team_tid as tid,
    people.person_id
from people
where
    people.origin_youth_team_tid is not null
    and (
        people.origin_team_tid is distinct from people.origin_youth_team_tid
        or people.origin_club_tid = people.origin_youth_team_tid
    )
union all
select
    'no club' as check_name,
    people.origin_club_tid as tid,
    people.person_id
from people
left join {{ ref('dim_club') }} as clubs
    on people.origin_club_tid = clubs.club_tid
where people.origin_youth_team_tid is not null and clubs.club_tid is null
union all
select
    'no academies' as check_name,
    null as tid,
    null as person_id
where not exists (
    select 1
    from people
    where people.origin_youth_team_tid is not null
)
