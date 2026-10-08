-- The shape of the web app's development lookups:
--   forecast inverted   site_forecast: within an attribute, age and horizon,
--                       a higher starting value never forecasts a median more
--                       than a point lower than the cell below it (the decode
--                       is monotone; an inversion is a broken lookup, not
--                       noise)
--   age curve           site_age_curve: the median yearly growth is never
--                       negative from 16 to 24, and falls from 16 to 20 to 24
-- One row per inverted cell or offending age.
with forecast as (
    select
        attribute,
        age_now,
        horizon_age,
        value_now,
        median,
        lag(median) over (
            partition by attribute, age_now, horizon_age order by value_now
        ) as previous_median
    from {{ ref('site_forecast') }}
),

curve as (
    select
        age,
        median
    from {{ ref('site_age_curve') }}
    where age between 16 and 24
)

select
    'forecast inverted' as check_name,
    attribute,
    age_now as age,
    horizon_age,
    value_now
from forecast
where median < previous_median - 1
union all
select
    'age curve negative' as check_name,
    null as attribute,
    age,
    null as horizon_age,
    null as value_now
from curve
where median < 0
union all
select
    'age curve not falling' as check_name,
    null as attribute,
    null as age,
    null as horizon_age,
    null as value_now
where not coalesce((
    select
        max(median) filter (where age = 16)
        >= max(median) filter (where age = 20)
        and max(median) filter (where age = 20)
        >= max(median) filter (where age = 24)
    from curve
), false)
