-- The fifteen position codes, from seeds/positions.csv: the unit each belongs
-- to (goalkeeper, defence, midfield, attack) and the order they are listed in.
-- The defensive wide positions (DML, DMR) are defence.
select
    code as position,
    unit,
    display_order
from {{ source('raw', 'positions') }}
