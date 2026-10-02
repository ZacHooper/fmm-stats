-- The events of our own matches, in order (seq) within each match (anchor).
-- event_type is decoded from type_byte by the loader (raw.event_types);
-- player_tid is the person credited and side his team's ('home' or 'away'),
-- an own goal's scorer included. minute is the minute the game shows, added
-- the stoppage time on top of it.
select
    cast(phase as date) as snapshot_date,
    anchor,
    seq,
    minute,
    added,
    min_display,
    tid as player_tid,
    side,
    type as event_type,
    type_byte,
    b0
from {{ source('raw', 'match_events') }}
