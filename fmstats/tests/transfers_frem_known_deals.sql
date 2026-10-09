{{ config(tags=['known_answers']) }}
-- Frem's biggest deals as the game's own screens list them, read from
-- site.transfers: the fee, the season he moved for and our direction. A row
-- for each deal missing or reading differently.
with career as (
    select * from {{ ref('stg_career') }}
),

expected (name, season, direction, fee_gbp) as (
    values
    ('Gregers Dehn', 2028, 'out', 14000000),
    ('Mads-Emil Wass', 2027, 'out', 12750000),
    ('Anosike Ementa', 2027, 'out', 9500000),
    ('Fillip Kaiser', 2028, 'in', 7383000),
    ('Adam Sørensen', 2028, 'in', 6000000)
),

actual as (
    select
        transfers.name,
        transfers.season,
        transfers.direction,
        transfers.fee_gbp
    from {{ ref('site_transfers') }} as transfers
    where
        transfers.direction is not null
        and transfers.transfer_type = 'permanent'
)

select
    expected.name,
    expected.fee_gbp as expected_fee,
    actual.fee_gbp as actual_fee
from expected
cross join career
left join actual
    on
        expected.name = actual.name
        and expected.season = actual.season
        and expected.direction = actual.direction
where
    career.career_key = 'frem'
    and actual.fee_gbp is distinct from expected.fee_gbp
