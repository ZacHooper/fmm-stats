-- The old raw.persons shape: first and last seen as phase strings.
select
    person_id,
    tid,
    dob,
    name,
    strftime(first_seen, '%Y-%m-%d') as first_seen,
    strftime(last_seen, '%Y-%m-%d') as last_seen,
    snapshots as slices
from {{ ref('int_persons') }}
