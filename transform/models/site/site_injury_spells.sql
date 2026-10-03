-- mart.injury_spells on the new layers: each injury (fact_injury_spell), its
-- season the one it starts in (seasons start on 1 July, var('site_calendar')).
select
    injuries.person_id,
    people.tid,
    people.name,
    'injured' as spell_type,
    cast(null as integer) as club_tid,
    cast(null as varchar) as club,
    {{ season_of('injuries.start_date') }} as season,
    injuries.start_date as valid_from,
    injuries.end_date as valid_to,
    cast(null as varchar) as arrival_window
from {{ ref('fact_injury_spell') }} as injuries
cross join {{ site_calendar() }} as career
left join {{ ref('dim_person') }} as people
    on injuries.person_id = people.person_id
