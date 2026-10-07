-- The match event type codes and their names, seeded by the loader from the
-- parser.
select
    code,
    name
from {{ source('raw', 'event_types') }}
