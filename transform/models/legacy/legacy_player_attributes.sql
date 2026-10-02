-- The old raw.player_attributes shape:
-- int.player_attributes on the (season, phase) key.
select
    {{ legacy_key() }},
    attributes.* exclude (snapshot_date)  -- noqa: RF02
from {{ ref('int_player_attributes') }} as attributes
{{ join_snapshots('attributes') }}
