-- The attributes the save states outright. The seven plain attributes always
-- come from the player's own record; for our squad, the entangled ones come
-- from his latest scrapbook entry while it is fresh. NULL where the save does
-- not state it.

with fresh_entries as (
    select entries.*
    from {{ ref('int_managed_squad') }} as squad
    inner join {{ ref('int_scrapbook_entries') }} as entries
        on
            squad.snapshot_date = entries.snapshot_date
            and squad.tid = entries.player_tid
    where entries.is_fresh
)

select
    stated.snapshot_date,
    stated.tid,
    {% for attribute in var('attr_order') %}
    {% if attribute in var('exact_single') %}
    stated."{{ attribute }}"{% if not loop.last %},{% endif %}
    {% else %}
    case
        when entry.player_tid is not null then entry."{{ attribute }}"
        else stated."{{ attribute }}"
    end as "{{ attribute }}"{% if not loop.last %},{% endif %}
    {% endif %}
    {% endfor %}
from {{ ref('stg_player_attributes_stated') }} as stated
left join fresh_entries as entry
    on
        stated.snapshot_date = entry.snapshot_date
        and stated.tid = entry.player_tid
