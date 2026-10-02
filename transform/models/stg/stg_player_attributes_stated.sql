-- The attributes the player's own record states outright, one row per player
-- per snapshot; NULL where the record does not state one.
select
    cast(phase as date) as snapshot_date,
    tid,
    {% for attribute in var('attr_order') %}
    "{{ attribute }}"{% if not loop.last %},{% endif %}
    {% endfor %}
from {{ source('raw', 'player_attributes_exact_raw') }}
