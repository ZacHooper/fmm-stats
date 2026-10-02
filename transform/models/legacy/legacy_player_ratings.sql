-- The old v_player_ratings shape: int.player_ratings on the (season, phase)
-- key.
select
    {{ legacy_key() }},
    ratings.tid,
    ratings.method,
    ratings.role,
    ratings.rating
from {{ ref('int_player_ratings') }} as ratings
{{ join_snapshots('ratings') }}
