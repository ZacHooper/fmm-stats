-- Each player's familiarity (0-20) with every position he has any for.
select
    cast(phase as date) as snapshot_date,
    tid,
    position,
    familiarity
from {{ source('raw', 'player_positions') }}
