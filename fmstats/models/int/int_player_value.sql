-- The transfer-value model scored for every player with the inputs it needs,
-- one row per (snapshot_date, tid). The save states a value only for our own
-- squad (int.player_info.value), so everyone else's is this estimate; the
-- coefficients are stg.value_model's, the inputs int.player_value_inputs'. A
-- player with no reputation, or no league reputation gets no row.
-- is_in_trusted_band: the estimate lies in var('value_trusted_band'), the
-- range the model was validated in.
{%- set terms = ['intercept', 'ca', 'pa', 'lrep', 'llrp', 'gk', 'acap', 'acap2',
    'res'] %}
{%- set band = var('value_trusted_band') %}

with coefficients as (
    select
            {% for term in terms %}
        max(coefficient) filter (where term = '{{ term }}') as {{ term }}
        {%- if not loop.last %},{% endif %}
            {% endfor %}
    from {{ ref('stg_value_model') }}
),

inputs as (
    select
        snapshot_date,
        tid,
        ca,
        pa,
        reputation,
        league_reputation,
        is_goalkeeper,
        is_reserve,
        least(age, {{ var('value_age_cap') }}) as capped_age
    from {{ ref('int_player_value_inputs') }}
),

scored as (
    select
        inputs.snapshot_date,
        inputs.tid,
        exp(
            coefficients.intercept
            + coefficients.ca * inputs.ca
            + coefficients.pa * inputs.pa
            + coefficients.lrep * ln(inputs.reputation)
            + coefficients.llrp * ln(inputs.league_reputation)
            + coefficients.gk * cast(inputs.is_goalkeeper as int)
            + coefficients.acap * inputs.capped_age
            + coefficients.acap2 * inputs.capped_age * inputs.capped_age
            + coefficients.res * cast(inputs.is_reserve as int)
        ) as estimate
    from inputs
    cross join coefficients
    where
        inputs.reputation > 0
        and inputs.league_reputation > 0
        and inputs.ca is not null
        and inputs.pa is not null
)

select
    snapshot_date,
    tid,
    cast(round(estimate) as bigint) as value_estimate,
    estimate between {{ band[0] }} and {{ band[1] }} as is_in_trusted_band
from scored
