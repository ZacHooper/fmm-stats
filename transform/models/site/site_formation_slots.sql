-- How many start at each position in each formation an AI manager can prefer
-- (var('formation_slots')), keyed (formation, position), in the order the var
-- lists them (formation_order, position_order).
select
    formation_slot_values.formation,
    formation_slot_values.position,
    formation_slot_values.slots,
    formation_slot_values.formation_order,
    formation_slot_values.position_order
from (
    values
    {% for formation, slots in var('formation_slots').items() %}
    {% set outer = loop %}
    {% for position, n in slots.items() %}
    (
        '{{ formation }}',
        '{{ position }}',
        {{ n }},
        {{ outer.index }},
        {{ loop.index }}
    )
    {%- if not (outer.last and loop.last) %},{% endif %}
    {% endfor %}
    {% endfor %}
) as formation_slot_values (
    formation, position, slots, formation_order, position_order
)
