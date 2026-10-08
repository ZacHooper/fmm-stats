-- The transfer-value model's coefficients, one row per term, from
-- seeds/value_model.csv (fitted offline by scripts/fit_value_model.py):
-- log(value) = intercept + the sum of each var('value_terms') term times its
-- coefficient; the terms are built in int.player_value_inputs.
select
    term,
    coefficient
from {{ source('raw', 'value_model') }}
