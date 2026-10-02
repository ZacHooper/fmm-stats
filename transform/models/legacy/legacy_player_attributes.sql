-- The old raw.player_attributes shape: the 23 displayed attributes from
-- int.player_attributes, each with an `_est` flag (true for an estimable
-- attribute of a player whose estimable attributes are decoded), on the
-- (season, phase) key.
{%- set estimable = estimable_attributes() %}

select
    {{ legacy_key() }},
    attributes.tid,
    {% for attribute in var('attr_order') %}
    {% set flag = 'is_estimated' if attribute in estimable else 'false' %}
    attributes."{{ attribute }}",
    {{ flag }} as "{{ attribute }}_est"{% if not loop.last %},{% endif %}
    {% endfor %}
from {{ ref('int_player_attributes') }} as attributes
{{ join_snapshots('attributes') }}
