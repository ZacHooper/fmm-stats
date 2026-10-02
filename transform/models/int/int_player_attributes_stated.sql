-- The attributes a player's own attribute record states outright: the seven
-- var('exact_single') attributes are its plain bytes as stored (Pace is
-- pace_src); every other attribute is NULL here, decoded or taken from a
-- scrapbook entry downstream. One row per player with an attribute record.
select
    snapshot_date,
    tid,
    {% for attribute in var('attr_order') %}
    {% if attribute in var('exact_single') %}
    {{ attribute | lower }}_src as "{{ attribute }}"
    {%- else %}
    cast(null as integer) as "{{ attribute }}"
    {%- endif %}{% if not loop.last %},{% endif %}
    {% endfor %}
from {{ ref('int_player_records') }}
where has_attributes
