-- Each tracked player's spells injured, in the off-season week and out on
-- loan, from the weekly Player Progress rows (our squad and reserves, back to
-- each player's first week at the club): one row per run of flagged weeks,
-- keyed (person_id, spell_type, start_date). var('progress_spells') names
-- each spell type's flag and the gap that ends a run. start_date and end_date
-- are its first and last flagged week, so the true dates lie within a week of
-- them. A week can be stored more than once in one save and in many
-- snapshots, so a week's flags are every copy's OR-ed together; a player's
-- weeks leave the save with him, so a departed player's come from the
-- snapshots taken while he was ours. A loan spell is not split at the season
-- boundary.
with weeks as (
    select
        people.person_id,
        progress.week_date,
        {% for flag in var('progress_bits') %}
        bool_or(progress.{{ flag }}) as {{ flag }}
        {%- if not loop.last %},{% endif %}
        {% endfor %}
    from {{ ref('stg_player_progress') }} as progress
    inner join {{ ref('int_person_snapshots') }} as people
        on
            progress.snapshot_date = people.snapshot_date
            and progress.tid = people.tid
    group by people.person_id, progress.week_date
),

flagged as (
    {% for spell_type, spell in var('progress_spells').items() %}
    select
        person_id,
        week_date,
        '{{ spell_type }}' as spell_type,
        {{ spell.gap_days }} as gap_days
    from weeks
    where {{ spell.flag }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

-- a run starts at a week more than gap_days after the last flagged one
numbered as (
    select
        person_id,
        spell_type,
        week_date,
        sum(starts_spell) over (
            partition by person_id, spell_type order by week_date
        ) as spell
    from (
        select
            *,
            case
                when
                    week_date - lag(week_date) over (
                        partition by person_id, spell_type order by week_date
                    ) <= gap_days
                    then 0
                else 1
            end as starts_spell
        from flagged
    ) as runs
)

select
    person_id,
    spell_type,
    min(week_date) as start_date,
    max(week_date) as end_date,
    count(*) as weeks
from numbered
group by person_id, spell_type, spell
