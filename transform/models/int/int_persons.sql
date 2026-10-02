-- One row per person across every snapshot, so a retired player whose slot has
-- gone to a newgen keeps his history. name is the latest one.
select
    {{ person_id('record.tid', 'record.dob') }} as person_id,
    record.tid,
    record.dob,
    arg_max(person_names.name, record.snapshot_date) as name,
    min(record.snapshot_date) as first_seen,
    max(record.snapshot_date) as last_seen,
    count(*) as snapshots
from {{ ref('stg_person_records') }} as record
left join {{ ref('int_person_names') }} as person_names
    on
        record.snapshot_date = person_names.snapshot_date
        and record.tid = person_names.tid
group by record.tid, record.dob
