-- Each player's familiarity with every position his attribute record rates
-- above 1, by tid.
select
    person.snapshot_date,
    person.tid,
    positions.position,
    positions.familiarity
from {{ ref('stg_person_records') }} as person
inner join {{ ref('stg_attribute_positions') }} as positions
    on
        person.snapshot_date = positions.snapshot_date
        and person.sid = positions.sid
