-- A player's spells of one type never overlap and never end before they
-- start: one team's books at a time, one loan or one injury at a time.
-- Spells of different types may overlap (injured while out on loan). Every
-- dated spell model is held to the same rule: site_player_spells (all four
-- types), fact_loan_spell's dates and snapshot bounds, fact_injury_spell.
with spells as (
    select
        person_id,
        spell_type,
        from_date,
        coalesce(to_date, date '9999-12-31') as to_date
    from {{ ref('site_player_spells') }}
)

select
    'two spells of one type overlap' as "check",  -- noqa: RF04
    spells.person_id,
    spells.spell_type,
    spells.from_date
from spells
inner join spells as later
    on
        spells.person_id = later.person_id
        and spells.spell_type = later.spell_type
        and spells.from_date < later.from_date
        and spells.to_date >= later.from_date
union all
select
    'a spell ends before it starts' as "check",  -- noqa: RF04
    person_id,
    spell_type,
    from_date
from spells
where to_date < from_date
union all
select
    'a loan ends before it starts' as "check",  -- noqa: RF04
    person_id,
    'loan' as spell_type,
    coalesce(start_date, first_seen_date) as from_date
from {{ ref('fact_loan_spell') }}
where
    end_date < start_date
    or last_seen_date < first_seen_date
    or (start_date is null) <> (end_date is null)
    or (first_seen_date is null) <> (last_seen_date is null)
union all
select
    'an injury ends before it starts' as "check",  -- noqa: RF04
    person_id,
    'injured' as spell_type,
    start_date as from_date
from {{ ref('fact_injury_spell') }}
where end_date < start_date or weeks < 1
