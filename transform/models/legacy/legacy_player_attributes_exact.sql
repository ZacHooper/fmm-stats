-- The old raw.player_attributes_exact shape:
-- int.player_attributes_exact on the (season, phase) key.
select
    {{ legacy_key() }},
    attributes.* exclude (snapshot_date)  -- noqa: RF02
from {{ ref('int_player_attributes_exact') }} as attributes
{{ join_snapshots('attributes') }}
