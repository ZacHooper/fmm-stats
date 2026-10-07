-- One row per person across every snapshot, so a retired player whose slot has
-- gone to a newgen keeps his history. name is the latest one. Static attributes
-- (ethnicity, height, weight, preferred squad number, footedness) come from the
-- latest snapshot they appear in.
with person_base as (
    select
        {{ person_id('record.tid', 'record.dob') }} as person_id,
        record.tid,
        record.dob,
        arg_max(person_names.name, record.snapshot_date) as name,
        arg_max(record.ethnicity, record.snapshot_date) as ethnicity,
        min(record.snapshot_date) as first_seen,
        max(record.snapshot_date) as last_seen,
        count(*) as snapshots
    from {{ ref('stg_persons') }} as record
    left join {{ ref('int_person_names') }} as person_names
        on
            record.snapshot_date = person_names.snapshot_date
            and record.tid = person_names.tid
    group by record.tid, record.dob
),

player_attrs as (
    select
        person.tid,
        person.dob,
        arg_max(attrs.height_cm, attrs.snapshot_date) as height_cm,
        arg_max(attrs.weight_kg, attrs.snapshot_date) as weight_kg,
        arg_max(attrs.preferred_squad_number, attrs.snapshot_date) as preferred_squad_number,
        arg_max(attrs.foot_left, attrs.snapshot_date) as foot_left,
        arg_max(attrs.foot_right, attrs.snapshot_date) as foot_right
    from {{ ref('stg_persons') }} as person
    inner join {{ ref('stg_player_attributes') }} as attrs
        on
            person.snapshot_date = attrs.snapshot_date
            and person.sid = attrs.sid
    group by person.tid, person.dob
)

select
    person_base.person_id,
    person_base.tid,
    person_base.dob,
    person_base.name,
    person_base.ethnicity,
    player_attrs.height_cm,
    player_attrs.weight_kg,
    player_attrs.preferred_squad_number,
    player_attrs.foot_left,
    player_attrs.foot_right,
    person_base.first_seen,
    person_base.last_seen,
    person_base.snapshots
from person_base
left join player_attrs
    on
        person_base.tid = player_attrs.tid
        and (
            person_base.dob = player_attrs.dob
            or (person_base.dob is null and player_attrs.dob is null)
        )

