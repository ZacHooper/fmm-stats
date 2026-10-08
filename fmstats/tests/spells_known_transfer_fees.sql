{{ config(tags=['known_answers']) }}
-- Three of Frem's deals at the fee the in-game Transfers screen reports. A
-- row for each deal missing or at another fee.
with career as (
    select * from {{ ref('stg_career') }}
),

expected (name, to_club, fee_gbp) as (
    values
    ('Mads-Emil Wass', 'Granada', 12750000),
    ('Anosike Ementa', 'Fenerbahçe A.Ş.', 9500000),
    ('Fillip Kaiser', 'Boldklubben Frem', 7383000)
),

actual as (
    select
        people.name,
        clubs.name as to_club,
        max(transfers.fee_gbp) as fee_gbp
    from {{ ref('fact_transfer') }} as transfers
    inner join {{ ref('dim_person') }} as people
        on transfers.person_id = people.person_id
    inner join {{ ref('dim_club') }} as clubs
        on transfers.to_club_tid = clubs.club_tid
    group by people.name, clubs.name
)

select
    expected.name,
    expected.to_club,
    expected.fee_gbp as expected_fee_gbp,
    actual.fee_gbp as actual_fee_gbp
from expected
cross join career
left join actual
    on
        expected.name = actual.name
        and expected.to_club = actual.to_club
where
    career.career_key = 'frem'
    and actual.fee_gbp is distinct from expected.fee_gbp
