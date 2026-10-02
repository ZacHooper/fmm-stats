-- Each staff member on each snapshot (a person with no attribute record link),
-- joined to his staff record on id2 where the save holds one
-- (has_staff_record): coaching ability, reputation, the manager's formation
-- triple with its names, and the two banded values the game displays, Style
-- (from attacking_intent) and the reputation tier (from world_reputation).
{%- set slots = ['preferred', 'attacking', 'defensive'] %}

select
    person.snapshot_date,
    person.tid,
    people.person_id,
    person_names.name,
    person.club_tid,
    staff.id2 is not null as has_staff_record,
    staff.* exclude (snapshot_date, id2),  -- noqa: RF02
    {% for slot in slots %}
    formation_{{ slot }}.name as formation_{{ slot }}_name,
    {% endfor %}
    case
        {% for ceiling, label in var('staff_tier_bands') %}
        when staff.world_reputation < {{ ceiling }} then '{{ label }}'
        {% endfor %}
    end as reputation_tier,
    case
        {% for ceiling, label in var('staff_style_bands') %}
        when staff.attacking_intent <= {{ ceiling }} then '{{ label }}'
        {% endfor %}
    end as style
from {{ ref('stg_person_records') }} as person
inner join {{ ref('int_person_snapshots') }} as people
    on
        person.snapshot_date = people.snapshot_date
        and person.tid = people.tid
left join {{ ref('int_person_names') }} as person_names
    on
        person.snapshot_date = person_names.snapshot_date
        and person.tid = person_names.tid
left join {{ ref('stg_staff_records') }} as staff
    on
        person.snapshot_date = staff.snapshot_date
        and person.id2 = staff.id2
{% for slot in slots %}
left join {{ ref('stg_formations') }} as formation_{{ slot }}
    on
        staff.snapshot_date = formation_{{ slot }}.snapshot_date
        and staff.formation_{{ slot }} = formation_{{ slot }}.formation_id
{% endfor %}
where person.sid is null
