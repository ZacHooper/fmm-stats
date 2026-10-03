-- Each tracked player's weeks, once: keyed (person_id, week_date), from every
-- snapshot's Player Progress rows. A save holds our squad and reserves back
-- to their first week at the club, and a week can be stored more than once in
-- one save, so every copy from every snapshot is OR-ed into one status; a
-- player's weeks leave the save with him, so a departed player's come from
-- the snapshots taken while he was ours. The flags are var('progress_bits').
select
    people.person_id,
    progress.week_date,
    any_value(progress.tid) as tid,
    bit_or(progress.status) as status,
    {% for flag, mask in var('progress_bits').items() %}
    bit_or(progress.status) & {{ mask }} <> 0 as {{ flag }}
    {%- if not loop.last %},{% endif %}
    {% endfor %}
from {{ ref('stg_player_progress') }} as progress
inner join {{ ref('int_person_snapshots') }} as people
    on
        progress.snapshot_date = people.snapshot_date
        and progress.tid = people.tid
group by people.person_id, progress.week_date
