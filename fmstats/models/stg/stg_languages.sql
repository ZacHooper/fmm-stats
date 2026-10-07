-- The language table, one row per language per snapshot. nation_id is the
-- language's home nation, NULL where it has none (var('no_id16')).
select
    cast(phase as date) as snapshot_date,
    id as language_id,
    uid,
    name,
    other_name,
    nullif(nation_id, {{ var('no_id16') }}) as nation_id,
    difficulty
from {{ source('raw', 'languages') }}
