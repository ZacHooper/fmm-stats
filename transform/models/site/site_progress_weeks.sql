-- mart.progress_weeks on the new layers: each tracked player's week, every
-- copy of it in every snapshot OR-ed together (stg_player_progress). week is
-- the old view's column name, a keyword kept as it is.
select
    progress.tid,
    any_value(people.person_id) as person_id,
    progress.week_date as week,  -- noqa: RF04
    bit_or(progress.status) as status,
    bool_or(progress.is_injured) as injured,
    bool_or(progress.is_off_season) as off_season,
    bool_or(progress.is_on_loan) as on_loan
from {{ ref('stg_player_progress') }} as progress
left join {{ ref('int_person_snapshots') }} as people
    on
        progress.snapshot_date = people.snapshot_date
        and progress.tid = people.tid
group by progress.tid, progress.week_date
