-- int_squad_training merges a player's intervals at one club before counting
-- months, and clips them to his home-grown window (the start of the season he
-- turns var('home_grown_window_ages')[0] to the end of the season he turns
-- the second) and to the snapshot. So no (player, club) holds more months
-- than that clipped window is long, give or take the rounding to 0.1 month:
-- a period credited twice by the two sources overlapping breaks the cap. One
-- row per (snapshot, player, club) over it.
{% set ages = var('home_grown_window_ages') %}
with career as (
    select * from {{ ref('stg_career') }}
),

windows as (
    select
        people.person_id,
        {{ season_start(
            season_of('people.dob + interval ' ~ ages[0] ~ ' year')
        ) }} as window_from,
        {{ season_end(
            season_of('people.dob + interval ' ~ ages[1] ~ ' year')
        ) }} as window_to
    from {{ ref('dim_person') }} as people
    cross join career
)

select
    training.snapshot_date,
    training.person_id,
    training.club_tid,
    training.months,
    round(
        date_diff(
            'day',
            windows.window_from,
            least(windows.window_to + 1, training.snapshot_date)
        )
        / {{ var('days_in_month') }},
        2
    ) as window_months
from {{ ref('int_squad_training') }} as training
inner join windows
    on training.person_id = windows.person_id
where
    training.months
    > date_diff(
        'day',
        windows.window_from,
        least(windows.window_to + 1, training.snapshot_date)
    )
    / {{ var('days_in_month') }}
    + 0.05
