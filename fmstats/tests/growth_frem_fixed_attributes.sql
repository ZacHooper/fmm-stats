{{ config(tags=['known_answers']) }}
-- Agility and Technique do not move between two exact reads a year apart in
-- Frem's squad, so site_forecast buckets them 'fixed' rather than projecting
-- growth that does not happen. One row per attribute not bucketed so.
with career as (
    select * from {{ ref('stg_career') }}
),

expected (attribute) as (
    values ('Agility'), ('Technique')
)

select
    expected.attribute,
    list(distinct forecast.bucket) as buckets
from expected
cross join career
left join {{ ref('site_forecast') }} as forecast
    on expected.attribute = forecast.attribute
where career.career_key = 'frem'
group by expected.attribute
having list(distinct forecast.bucket) is distinct from ['fixed']
