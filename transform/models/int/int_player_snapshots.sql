-- Each player on each snapshot (staff are not players): his own record, the
-- name and value our squad's scrapbook entries give, his current contract and
-- his training. club_tid is the club whose books he is on, from his record;
-- which team he plays in is int.team_squads'. For a player in our squad the
-- name comes from his latest entry, and the value from it while it is fresh
-- (the record holds no value); scrapbook_entry_date says which entry that was.

with squad_entries as (
    select entries.*
    from {{ ref('int_managed_squad') }} as squad
    inner join {{ ref('int_scrapbook_entries') }} as entries
        on
            squad.snapshot_date = entries.snapshot_date
            and squad.tid = entries.player_tid
)

select
    record.snapshot_date,
    record.tid,
    people.person_id,
    coalesce(entry.full_name, person_names.name) as name,
    record.club_tid,
    record.nationality_id,
    record.second_nationality_id,
    record.ethnicity,
    record.is_goalkeeper,
    record.ca,
    record.pa,
    record.reputation,
    record.current_reputation,
    record.world_reputation,
    record.foot_left,
    record.foot_right,
    record.height_cm,
    record.weight_kg,
    record.squad_number,
    record.preferred_squad_number,
    {% for column in var('hidden_attributes') + var('personality') %}
    record.{{ column }},
    {% endfor %}
    record.international_retired,
    record.international_caps,
    record.international_goals,
    record.u21_caps,
    record.u21_goals,
    record.joined_date,
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
from {{ ref('stg_persons') }} as record
inner join {{ ref('int_person_snapshots') }} as people
    on
        record.snapshot_date = people.snapshot_date
        and record.tid = people.tid
left join {{ ref('int_person_names') }} as person_names
    on
        record.snapshot_date = person_names.snapshot_date
        and record.tid = person_names.tid
left join squad_entries as entry
    on
        record.snapshot_date = entry.snapshot_date
        and record.tid = entry.player_tid
left join {{ ref('stg_contracts') }} as contracts
    on
        record.snapshot_date = contracts.snapshot_date
        and record.tid = contracts.tid
        and contracts.is_current
left join {{ ref('stg_training') }} as training
    on
        record.snapshot_date = training.snapshot_date
        and record.tid = training.tid
where not record.is_staff
