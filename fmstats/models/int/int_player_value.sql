-- The transfer-value model scored for every player with the inputs it needs,
-- one row per (snapshot_date, tid). The save states a value only for our own
-- squad (int.player_info.value), so everyone else's is this estimate:
-- log(value) = intercept + the sum of each var('value_terms') term
-- (int.player_value_inputs) times its stg.value_model coefficient. A player
-- with any term missing gets no row.
-- is_in_trusted_band: the estimate lies in var('value_trusted_band'), the
-- range the model was validated in.
{%- set terms = var('value_terms') %}
{%- set band = var('value_trusted_band') %}

with coefficients as (
    select
        max(coefficient) filter (where term = 'intercept') as intercept,
        {% for term in terms %}
        max(coefficient) filter (where term = '{{ term }}') as {{ term }}
        {%- if not loop.last %},{% endif %}
        {% endfor %}
    from {{ ref('stg_value_model') }}
),

scored as (
    select
        inputs.snapshot_date,
        inputs.tid,
        exp(
            coefficients.intercept
            {% for term in terms %}
            + coefficients.{{ term }} * inputs.{{ term }}
            {% endfor %}
        ) as estimate
    from {{ ref('int_player_value_inputs') }} as inputs
    cross join coefficients
    where
        inputs.{{ terms[0] }} is not null
        {% for term in terms[1:] %}
        and inputs.{{ term }} is not null
        {% endfor %}
)

select
    snapshot_date,
    tid,
    cast(round(estimate) as bigint) as value_estimate,
    estimate between {{ band[0] }} and {{ band[1] }} as is_in_trusted_band
from scored
