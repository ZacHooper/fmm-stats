-- The old raw.player_positions shape: one row per position a player's record
-- rates, from int.player_records' pos_* columns, on the (season, phase) key.
with long as (
    unpivot {{ ref('int_player_records') }}
    on
    {% for position in var('positions') %}
    pos_{{ position | lower }}{% if not loop.last %},{% endif %}
    {% endfor %}
    into name position_column value familiarity
)

select
    {{ legacy_key() }},
    long.tid,
    upper(replace(long.position_column, 'pos_', '')) as position,
    long.familiarity
from long
{{ join_snapshots('long') }}
