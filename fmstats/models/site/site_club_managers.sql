-- Each team's current manager, keyed team_tid: his name, his three
-- formations (preferred, attacking, defensive) and his Style, as the save
-- holds them on the latest snapshot.
select
    spells.team_tid,
    spells.person_id,
    persons.name,
    staff.formation_preferred_name as formation_preferred,
    staff.formation_attacking_name as formation_attacking,
    staff.formation_defensive_name as formation_defensive,
    staff.style
from {{ ref('fact_staff_spell') }} as spells
inner join {{ ref('fact_staff_snapshot') }} as staff
    on
        spells.person_id = staff.person_id
        and staff.is_current
left join {{ ref('dim_person') }} as persons
    on spells.person_id = persons.person_id
where spells.role = 'manager' and spells.is_current
