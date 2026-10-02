-- The attributes the save states outright. The seven plain attributes always
-- come from the player's own record; for our squad, the entangled ones come
-- from his entry while it is fresh. NULL where the save does not state it.
select
    stated.season,
    stated.phase,
    stated.tid,
    {% for attribute in var('attr_order') %}
    {% if attribute in var('exact_single') %}
    stated."{{ attribute }}"{% if not loop.last %},{% endif %}
    {% else %}
    case
        when {{ fresh_entry() }} then entry."{{ attribute }}"
        else stated."{{ attribute }}"
    end as "{{ attribute }}"{% if not loop.last %},{% endif %}
    {% endif %}
    {% endfor %}
from {{ source('raw', 'player_attributes_exact_raw') }} as stated
left join {{ ref('int_squad_scrapbook') }} as entry
    on
        stated.season = entry.season
        and stated.phase = entry.phase
        and stated.tid = entry.tid
