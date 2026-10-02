-- Every attribute the save does not always state, decoded from the player's
-- own attribute record (macros/attribute_decode.sql), whether or not the save
-- also states it on this snapshot. The two composites are closed forms over two
-- plain 1-20 attribute columns: Teamwork's is exact, Aerial's matches about
-- 71% of the time. The other entangled attributes come from their fitted
-- coefficients in stg.attribute_model. int.player_attributes chooses between
-- these and the stated values.
{%- set spec = attribute_model() %}
{%- set composites = var('composites') %}
{%- set always_stated = var('exact_single') %}
{%- set decoded = var('attr_order') | reject('in', always_stated) | list %}

select
    person.snapshot_date,
    person.tid,
    {% for attribute in decoded %}
    {% set c = composites.get(attribute) %}
    {% if c %}
    {% set expr = composite(c.columns[0], c.columns[1], c.w) %}
    {% elif not execute %}
    {% set expr = 'null' %}{# spec is read when the model runs, not at parse #}
    {% elif attribute in spec %}
    {% set expr = model_expr(spec[attribute]) %}
    {% else %}
    {% do exceptions.raise_compiler_error("no decode for " ~ attribute) %}
    {% endif %}
    {{ expr }} as "{{ attribute }}"{% if not loop.last %},{% endif %}
    {% endfor %}
from {{ ref('stg_persons') }} as person
inner join {{ ref('stg_player_attributes') }} as record
    on
        person.snapshot_date = record.snapshot_date
        and person.sid = record.sid
-- the decode macros read stg.attribute_model
-- depends_on: {{ ref('stg_attribute_model') }}
