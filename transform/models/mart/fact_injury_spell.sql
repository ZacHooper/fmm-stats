-- Each injury of a player we have tracked (our squad and reserves, Player
-- Progress), keyed (person_id, start_date): a run of injured weeks, a new
-- spell wherever the next injured week is more than
-- var('injury_spell_gap_days') after the last. start_date and end_date are
-- the first and last injured week, so the true dates lie within a week of
-- them; training injuries are included. Not split at the season boundary: an
-- injury runs on over the summer.
with injured as (
    select
        person_id,
        week_date,
        case
            when
                week_date - lag(week_date) over (
                    partition by person_id order by week_date
                ) <= {{ var('injury_spell_gap_days') }}
                then 0
            else 1
        end as starts_spell
    from {{ ref('int_progress_weeks') }}
    where is_injured
),

numbered as (
    select
        person_id,
        week_date,
        sum(starts_spell) over (
            partition by person_id order by week_date
        ) as spell
    from injured
)

select
    person_id,
    min(week_date) as start_date,
    max(week_date) as end_date,
    count(*) as weeks
from numbered
group by person_id, spell
