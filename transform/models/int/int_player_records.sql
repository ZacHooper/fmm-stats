-- Each player's person record joined to his attribute record (on sid), one
-- row per player per snapshot; staff (no sid) are not players.
-- has_attributes says whether the save holds an attribute record for him, and
-- every attribute-record column is NULL when it does not. is_goalkeeper: his
-- goalkeeper familiarity is 20.
select
    person.*,
    attributes.sid is not null as has_attributes,
    case
        when attributes.sid is not null
            then coalesce(
                cast(json_extract(attributes.positions, '$.GK') as integer), 0
            ) = 20
    end as is_goalkeeper,
    attributes.* exclude (snapshot_date, sid)  -- noqa: RF02
from {{ ref('stg_person_records') }} as person
left join {{ ref('stg_attribute_records') }} as attributes
    on
        person.snapshot_date = attributes.snapshot_date
        and person.sid = attributes.sid
where person.sid is not null
