-- Each player on each snapshot (staff are not players): who he is and where
-- he stands, everything except how he is rated (int.player_attributes). His
-- person record joined to his attribute record on sid for the record's tail;
-- has_attributes says whether the save holds one. club_tid is the club whose
-- books he is on, from his record; which team he plays in is
-- int.team_squads'. For a player in our squad the name comes from his latest
-- scrapbook entry, and the value from it while it is fresh (the record holds
-- no value); scrapbook_entry_date says which entry that was. is_goalkeeper:
-- his goalkeeper familiarity is 20.

with squad_entries as (
    select entries.*
    from {{ ref('int_managed_squad') }} as squad
    inner join {{ ref('int_scrapbook_entries') }} as entries
        on
            squad.snapshot_date = entries.snapshot_date
            and squad.tid = entries.player_tid
)

select
    person.snapshot_date,
    person.tid,
    person.sid,
    people.person_id,
    coalesce(entry.full_name, person_names.name) as name,
    person.club_tid,
    person.nationality_id,
    person.second_nationality_id,
    person.ethnicity,
    record.sid is not null as has_attributes,
    case
        when record.sid is not null then coalesce(record.pos_gk, 0) = 20
    end as is_goalkeeper,
    record.ca,
    record.pa,
    record.reputation,
    record.current_reputation,
    record.world_reputation,
    record.height_cm,
    record.weight_kg,
    record.squad_number,
    record.preferred_squad_number,
    record.international_retired,
    person.international_caps,
    person.international_goals,
    person.u21_caps,
    person.u21_goals,
    person.joined_date,
    case when entry.is_fresh then entry.value end as value,
    contracts.wage_units,
    cast(contracts.wage_units as bigint)
    * {{ var('wage_gbp_per_unit') }} as wage_gbp,
    contracts.start_date as contract_start,
    contracts.expiry as contract_expiry,
    training.intensity as training_intensity,
    training.focus_role as training_focus_role,
    training.focus_attribute as training_focus_attribute,
    training.focus_position as training_focus_position,
    case when entry.is_fresh then entry.entry_date end as scrapbook_entry_date
from {{ ref('stg_persons') }} as person
inner join {{ ref('int_person_snapshots') }} as people
    on
        person.snapshot_date = people.snapshot_date
        and person.tid = people.tid
left join {{ ref('stg_player_attributes') }} as record
    on
        person.snapshot_date = record.snapshot_date
        and person.sid = record.sid
left join {{ ref('int_person_names') }} as person_names
    on
        person.snapshot_date = person_names.snapshot_date
        and person.tid = person_names.tid
left join squad_entries as entry
    on
        person.snapshot_date = entry.snapshot_date
        and person.tid = entry.player_tid
left join {{ ref('stg_contracts') }} as contracts
    on
        person.snapshot_date = contracts.snapshot_date
        and person.tid = contracts.tid
        and contracts.is_current
left join {{ ref('stg_training') }} as training
    on
        person.snapshot_date = training.snapshot_date
        and person.tid = training.tid
where person.sid is not null
