{{ config(tags=['known_answers']) }}
-- Two of Frem's spells as the Player Progress page bands them: Magnus
-- Davidsen out on loan 2023-07-14 to 2024-06-01, Johan Nordberg injured
-- 2023-08-15 to 2024-03-02. And spells of different types do overlap: at
-- least one of our players was injured while out on loan.
with career as (
    select * from {{ ref('stg_career') }}
),

spells as (
    select
        people.name,
        spells.person_id,
        spells.spell_type,
        spells.from_date,
        spells.to_date
    from {{ ref('site_player_spells') }} as spells
    inner join {{ ref('dim_person') }} as people
        on spells.person_id = people.person_id
),

expected (name, spell_type, from_date, to_date) as (
    values
    ('Magnus Davidsen', 'loan_out', date '2023-07-14', date '2024-06-01'),
    ('Johan Nordberg', 'injured', date '2023-08-15', date '2024-03-02')
),

injured_on_loan as (
    select count(*) as n
    from spells as injuries
    inner join spells as loans
        on
            injuries.person_id = loans.person_id
            and injuries.from_date <= loans.to_date
            and injuries.to_date >= loans.from_date
    where
        injuries.spell_type = 'injured'
        and loans.spell_type = 'loan_out'
)

select
    'a known spell is missing' as "check",  -- noqa: RF04
    expected.name,
    expected.spell_type,
    expected.from_date
from expected
cross join career
where
    career.career_key = 'frem'
    and not exists (
        select 1 as found
        from spells
        where
            spells.name = expected.name
            and spells.spell_type = expected.spell_type
            and spells.from_date = expected.from_date
            and spells.to_date = expected.to_date
    )
union all
select
    'no injury overlaps a loan out' as "check",  -- noqa: RF04
    null as name,
    null as spell_type,
    null as from_date
from injured_on_loan
cross join career
where career.career_key = 'frem' and injured_on_loan.n = 0
