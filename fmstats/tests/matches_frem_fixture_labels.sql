{{ config(tags=['known_answers']) }}
-- Frem's in-game fixture screens for 2026/27 and 2027/28, as site.matches
-- labels them: each match's stage and, in a two-legged tie, its leg. One row
-- per screen label the store holds differently or not at all; none for
-- another career.
with career as (
    select * from {{ ref('stg_career') }}
    where career_key = 'frem'
),

screens as (
    select
        screen_rows.match_date,
        screen_rows.stage,
        screen_rows.leg
    from (
        values
        -- Hajduk Split
        (date '2026-08-13', 'League Path · Third Qualifying Round', 2),
        (date '2026-08-20', 'Playoff', 1),  -- Olympiacos
        (date '2026-09-17', 'Group D', null),  -- Lyon
        (date '2026-09-24', 'Third Round', null),  -- Roskilde, Pokalen
        (date '2026-08-09', 'Preliminary Phase', null),  -- AGF, Superliga
        (date '2027-02-18', 'First Knockout Round', 1),  -- Leipzig
        (date '2027-04-04', 'Championship Group', null),  -- Nordsjælland
        -- Rangers
        (date '2027-08-04', 'League Path · Third Qualifying Round', 1)
    ) as screen_rows (match_date, stage, leg)
)

select
    screens.match_date,
    screens.stage as expected_stage,
    screens.leg as expected_leg,
    ours.stage as actual_stage,
    ours.leg as actual_leg
from screens
cross join career
left join {{ ref('site_matches') }} as ours
    on screens.match_date = ours.match_date
where
    ours.stage is distinct from screens.stage
    or ours.leg is distinct from screens.leg
