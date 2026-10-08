{{ config(tags=['known_answers']) }}
-- Five of Frem's players as the in-game Training screen showed them on
-- 2027-06-15: focus position, Focus Role, Attr and intensity (2 is Normal, 3
-- High). A row for each player missing or shown differently.
with career as (
    select * from {{ ref('stg_career') }}
),

expected (name, focus_position, focus_role, focus_attribute, intensity) as (
    values
    ('Gregers Dehn', 'DL', 'Wing-Back', 'CRE', 3),
    ('Andreas Garly', 'MC', 'Box to Box Midfielder', 'STR', 3),
    ('Aske Fredeløkke', 'GK', 'Sweeper Keeper', 'HAN', 2),
    ('Johannes Tjørnelund', 'DMC', 'Ball Winning Midfielder', 'STR', 2),
    ('Ruben Minerba', 'DC', 'Central Defender', 'AIR', 2)
),

actual as (
    select
        people.name,
        players.training_focus_position as focus_position,
        roles.name as focus_role,
        attributes.abbrev as focus_attribute,
        players.training_intensity as intensity
    from {{ ref('fact_player_snapshot') }} as players
    inner join {{ ref('dim_person') }} as people
        on players.person_id = people.person_id
    left join {{ ref('dim_role') }} as roles
        on players.training_focus_role = roles.role_id
    left join {{ ref('stg_training_attributes') }} as attributes
        on players.training_focus_attribute = attributes.code
    where players.snapshot_date = date '2027-06-15'
)

select
    expected.name,
    actual.focus_position,
    actual.focus_role,
    actual.focus_attribute,
    actual.intensity
from expected
cross join career
left join actual
    on expected.name = actual.name
where
    career.career_key = 'frem'
    and (
        actual.name is null
        or actual.focus_position is distinct from expected.focus_position
        or actual.focus_role is distinct from expected.focus_role
        or actual.focus_attribute is distinct from expected.focus_attribute
        or actual.intensity is distinct from expected.intensity
    )
