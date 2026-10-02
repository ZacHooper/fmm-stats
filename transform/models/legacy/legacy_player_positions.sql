-- The old raw.player_positions shape: int.player_positions on the
-- (season, phase) key.
select
    {{ legacy_key() }},
    positions.tid,
    positions.position,
    positions.familiarity
from {{ ref('int_player_positions') }} as positions
{{ join_snapshots('positions') }}
