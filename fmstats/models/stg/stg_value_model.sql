-- The transfer-value model's coefficients, one row per term, from
-- seeds/value_model.csv (fitted offline by scripts/fit_value_model.py):
-- log(value) = intercept + ca*CA + pa*PA + lrep*ln(reputation)
-- + llrp*ln(league reputation) + gk*is_goalkeeper + acap*A + acap2*A^2
-- + res*is_reserve, where A is his age capped at var('value_age_cap').
select
    term,
    coefficient
from {{ source('raw', 'value_model') }}
