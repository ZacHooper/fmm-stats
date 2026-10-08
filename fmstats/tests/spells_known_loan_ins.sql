{{ config(tags=['known_answers']) }}
-- Frem's loans in, as the game's own screens list them: each player's first
-- seasons on loan to the club we manage. The known seasons are a prefix of
-- the store's, not all of them: a loan still open when it was written down
-- (Tochi Chukwuani's, Lauge Gülstorff's) gains a season with each later
-- snapshot that still lists him. A row for each loan-in missing or starting
-- differently.
with career as (
    select * from {{ ref('stg_career') }}
),

expected (name, seasons) as (
    values
    ('Emil Højlund', [2022]),
    ('Marcelo Randolf', [2022]),
    ('Daniel Bisgaard Haarbo', [2022]),
    ('Ernest Nuamah', [2022, 2023]),
    ('Jeppe Erenbjerg', [2023]),
    ('Nicklas Strunck', [2023]),
    ('Marc Nielsen', [2023, 2024]),
    ('Jeppe Corfitzen', [2023, 2024]),
    ('Jonas Jensen-Abbew', [2024]),
    ('Andreas Schjelderup', [2025]),
    ('Emil Rosberg Møller', [2025]),
    ('Marinus Larsen', [2025]),
    ('Mounir Secka', [2025]),
    ('Tochi Chukwuani', [2025, 2026]),
    ('Lauge Gülstorff', [2026]),
    ('Mikkel Lejbowicz', [2026]),
    ('Oliver Sørensen', [2026]),
    ('Oliver Jeppe', [2028])
),

actual as (
    select
        people.name,
        list(distinct loans.season order by loans.season) as seasons
    from {{ ref('fact_loan_spell') }} as loans
    inner join career
        on loans.borrowing_club_tid = career.managed_club_tid
    inner join {{ ref('dim_person') }} as people
        on loans.person_id = people.person_id
    group by people.name
)

select
    expected.name,
    expected.seasons as expected_seasons,
    actual.seasons as actual_seasons
from expected
cross join career
left join actual
    on expected.name = actual.name
where
    career.career_key = 'frem'
    and actual.seasons[1:len(expected.seasons)]
    is distinct from expected.seasons
