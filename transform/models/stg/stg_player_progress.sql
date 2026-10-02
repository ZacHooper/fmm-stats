-- The weekly Player Progress table, every used row as stored: the managed
-- squad and reserves, back to each player's first week at the club. A week can
-- appear more than once and the copies can disagree, so there is no key.
-- status is the stored bitfield, its known bits named (var('progress_bits')):
-- injured that week (training injuries included), the off-season week at the
-- season boundary, and out on loan (never set on a loan in). Bits 3 and 6 are
-- unnamed. line_0 .. line_5 are the graph's six skill lines, 1-20; which line
-- is which is not yet known.
select
    cast(phase as date) as snapshot_date,
    tid,
    week as week_date,
    status,
    {% for flag, mask in var('progress_bits').items() %}
    status & {{ mask }} <> 0 as {{ flag }},
    {% endfor %}
    line_0,
    line_1,
    line_2,
    line_3,
    line_4,
    line_5
from {{ source('raw', 'player_progress') }}
