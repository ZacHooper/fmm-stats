-- mart.loan_out_spells on the new layers, its rules unchanged: each run of our
-- players' weeks on loan (int.progress_spells), split into the seasons it
-- touches and clipped to each. Seasons start on 1 July (var('site_calendar')).
-- The borrowing club is left NULL, as the old view has it (fact_loan_spell
-- names it).
with split as (
    select
        spells.person_id,
        spells.start_date,
        spells.end_date,
        unnest(
            range(
                {{ season_of('spells.start_date') }},
                {{ season_of('spells.end_date') }} + 1
            )
        ) as s
    from {{ ref('int_progress_spells') }} as spells
    cross join {{ site_calendar() }} as career
    where spells.spell_type = 'on_loan'
)

select
    split.person_id,
    people.tid,
    people.name,
    'loan_out' as spell_type,
    cast(null as integer) as club_tid,
    cast(null as varchar) as club,
    split.s as season,
    greatest(split.start_date, {{ season_start('split.s') }}) as valid_from,
    least(split.end_date, {{ season_end('split.s') }}) as valid_to,
    cast(null as varchar) as arrival_window
from split
cross join {{ site_calendar() }} as career
left join {{ ref('dim_person') }} as people
    on split.person_id = people.person_id
where
    greatest(split.start_date, {{ season_start('split.s') }})
    <= least(split.end_date, {{ season_end('split.s') }})
