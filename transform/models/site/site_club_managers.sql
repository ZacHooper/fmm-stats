-- mart.club_managers on the new layers: each team's manager on each snapshot,
-- the manager spells of fact_staff_spell, in site.staff's shape.
select staff.*
from {{ ref('site_staff') }} as staff
inner join {{ ref('fact_staff_spell') }} as spells
    on
        staff.club_tid = spells.team_tid
        and staff.phase_date
        between spells.first_seen_date and spells.last_seen_date
        and spells.role = 'manager'
inner join {{ ref('int_person_snapshots') }} as people
    on
        staff.phase_date = people.snapshot_date
        and staff.tid = people.tid
        and spells.person_id = people.person_id
