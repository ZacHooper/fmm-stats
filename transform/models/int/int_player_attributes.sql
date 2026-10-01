-- All 23 attributes with an `_est` flag each: stated where the save states
-- them, decoded from the record's attribute columns and stg.attribute_model
-- otherwise (macros/attribute_decode.sql). The two composites are closed forms
-- over two plain 1-20 attribute columns: Teamwork's is exact (`_est` false),
-- Aerial's matches about 71% of the time, so it is an estimate.
{%- set spec = attribute_model() %}
{%- set composites = var('composites') %}

select
    record.season,
    record.phase,
    record.tid,
    {% for attribute in var('attr_order') %}
    {% set stated = 'stated."' ~ attribute ~ '"' %}
    {% set c = composites.get(attribute) %}
    {% if c %}
    {% set derived = composite(c.columns[0], c.columns[1], c.w) %}
    {% elif attribute in spec %}
    {% set derived = model_expr(spec[attribute]) %}
    {% else %}
    {% set derived = none %}
    {% endif %}
    {% set estimated = (c and c.estimate) or (not c and attribute in spec) %}
    {% set flag = '(' ~ stated ~ ' is null)' if estimated else 'false' %}
    {% if derived %}
    coalesce({{ stated }}, {{ derived }}) as "{{ attribute }}",
    {% else %}
    {{ stated }} as "{{ attribute }}",
    {% endif %}
    {{ flag }} as "{{ attribute }}_est"{% if not loop.last %},{% endif %}
    {% endfor %}
from {{ ref('int_players') }} as record
inner join {{ ref('int_player_attributes_exact') }} as stated
    on
        record.season = stated.season
        and record.phase = stated.phase
        and record.tid = stated.tid
-- depends_on: {{ ref('stg_attribute_model') }} (read by attribute_model())
