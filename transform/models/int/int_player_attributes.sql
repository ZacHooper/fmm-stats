-- All 23 attributes with an `_est` flag each: the stated value where the save
-- states it, otherwise the decoded one from int.player_attribute_estimates.
-- `_est` is true when the value shown is a decode that can be wrong; Teamwork's
-- closed form is exact, so its flag is always false.
{%- set composites = var('composites') %}

select
    stated.snapshot_date,
    stated.tid,
    {% for attribute in var('attr_order') %}
    {% set c = composites.get(attribute) %}
    {% set value = 'stated."' ~ attribute ~ '"' %}
    {% if attribute in var('exact_single') %}
    {% set flag = 'false' %}
    {% else %}
    {% set flag = 'false' if c and not c.estimate else value ~ ' is null' %}
    {% set value = 'coalesce(' ~ value ~ ', estimate."' ~ attribute ~ '")' %}
    {% endif %}
    {{ value }} as "{{ attribute }}",
    {{ flag }} as "{{ attribute }}_est"{% if not loop.last %},{% endif %}
    {% endfor %}
from {{ ref('int_player_attributes_exact') }} as stated
inner join {{ ref('int_player_attribute_estimates') }} as estimate
    on
        stated.snapshot_date = estimate.snapshot_date
        and stated.tid = estimate.tid
