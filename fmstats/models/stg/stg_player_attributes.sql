-- The player attribute table, one record per player who has one, keyed by
-- sid: the 34 attribute bytes (the 16 entangled *_src bytes raw, the nine
-- plain *_src bytes, the nine hidden attributes), his familiarity with each
-- position (pos_gk .. pos_dmr; NULL where the record rates it 1, the floor),
-- feet, CA/PA and the record's tail.
select
    cast(phase as date) as snapshot_date,
    sid,
    {% for position in var('positions') %}
    cast(
        json_extract(positions, '$.{{ position }}') as integer
    ) as pos_{{ position | lower }},
    {% endfor %}
    foot_left,
    foot_right,
    ca,
    pa,
    reputation,
    current_reputation,
    world_reputation,
    international_retired,
    squad_number,
    preferred_squad_number,
    height_cm,
    weight_kg,
    {% for column in var('hidden_attributes') %}
    {{ column }},
    {% endfor %}
    {% for column in var('attribute_columns').values()
        if column not in var('hidden_attributes') %}
    {{ column }}{% if not loop.last %},{% endif %}
    {% endfor %}
from {{ source('raw', 'attribute_records') }}
