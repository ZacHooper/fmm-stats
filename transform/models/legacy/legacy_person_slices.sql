-- The old raw.person_slices shape: (season, phase, tid) -> person_id.
select
    {{ legacy_key() }},
    people.tid,
    people.person_id
from {{ ref('int_person_snapshots') }} as people
{{ join_snapshots('people') }}
