-- The weekly Player Progress table, every used row as stored: the managed
-- squad and reserves, back to each player's first week at the club. A week can
-- appear more than once and the copies can disagree, so there is no key.
-- status is the stored bitfield; line_0 .. line_5 are the six plotted lines.
select
    cast(phase as date) as snapshot_date,
    tid,
    week as week_date,
    status,
    line_0,
    line_1,
    line_2,
    line_3,
    line_4,
    line_5
from {{ source('raw', 'player_progress') }}
