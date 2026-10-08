{{ config(tags=['known_answers']) }}
-- Frem's registration rules (a house rule, docs/danish-registration-rules.md)
-- on every snapshot: a 25-man A-list, and the home-grown minimums of 8, 4 of
-- them club-trained, binding in the top two tiers only. Frem played in tier 4
-- (3. Division) to 2022-06-29, tier 3 to 2023-06-29, tier 2 (NordicBet Liga)
-- to 2024-06-28 and the 3F Superliga from 2024-06-30 through 2028-05-09, the
-- last snapshot this was read against. One row per snapshot to then with no
-- rules row, or rules or a tier other than these.
with career as (
    select * from {{ ref('stg_career') }}
),

expected as (
    select
        snapshot_date,
        case
            when snapshot_date <= '2022-06-29' then 4
            when snapshot_date <= '2023-06-29' then 3
            when snapshot_date <= '2024-06-28' then 2
            else 1
        end as tier
    from {{ ref('stg_snapshots') }}
    where snapshot_date <= '2028-05-09'
)

select
    expected.snapshot_date,
    expected.tier as expected_tier,
    rules.tier,
    rules.a_list_max,
    rules.hg_min,
    rules.hg_club_min
from expected
cross join career
left join {{ ref('site_registration_rules') }} as rules
    on expected.snapshot_date = rules.snapshot_date
where
    career.career_key = 'frem'
    and (
        rules.tier is distinct from expected.tier
        or rules.a_list_max is distinct from 25
        or rules.hg_min is distinct from (
            case when expected.tier <= 2 then 8 else 0 end
        )
        or rules.hg_club_min is distinct from (
            case when expected.tier <= 2 then 4 else 0 end
        )
    )
