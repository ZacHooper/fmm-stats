-- The attributes the save states outright, one row per player with an
-- attribute record. The seven var('exact_single') attributes are his record's
-- plain bytes as stored (Pace is pace_src); for our squad, the entangled ones
-- come from his latest scrapbook entry while it is fresh. NULL where the save
-- does not state it.

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
    record.snapshot_date,
    record.tid,
    {% for attribute in var('attr_order') %}
    {% if attribute in var('exact_single') %}
    record.{{ attribute | lower }}_src as "{{ attribute }}"
    {%- else %}
    entry."{{ attribute }}"
    {%- endif %}{% if not loop.last %},{% endif %}
    {% endfor %}
from {{ ref('int_player_records') }} as record
left join fresh_entries as entry
    on
        record.snapshot_date = entry.snapshot_date
        and record.tid = entry.player_tid
where record.has_attributes
