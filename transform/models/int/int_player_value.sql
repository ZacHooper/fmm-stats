-- The transfer-value model scored for every player with the inputs it needs,
-- one row per (snapshot_date, tid). The save states a value only for our own
-- squad (int.player_info.value), so everyone else's is this estimate; the
-- coefficients are stg.value_model's. The model's league reputation is that of
-- the league his team plays in (int.team_leagues); a reserve side's is its
-- first team's, with is_reserve set, as the model was fitted. A player with
-- no reputation, or no league reputation gets no row.
-- is_in_trusted_band: the estimate lies in var('value_trusted_band'), the
-- range the model was validated in.
-- Which league counts is a CASE over both joins, not a condition on the team
-- in either join's ON: a condition on the left side alone turns DuckDB's hash
-- join into a nested loop over every (player, team-league) pair.
{%- set terms = ['intercept', 'ca', 'pa', 'lrep', 'llrp', 'gk', 'acap', 'acap2',
    'res'] %}
{%- set reserve = var('team_types')[2] %}
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
        player.snapshot_date,
        player.tid,
        player.ca,
        player.pa,
        player.reputation,
        case
            when teams.team_type = '{{ reserve }}'
                then first_league.league_reputation
            else own_league.league_reputation
        end as league_reputation,
        player.is_goalkeeper,
        coalesce(teams.team_type = '{{ reserve }}', false) as is_reserve,
        least(
            {{ age_on('person.dob', 'player.snapshot_date') }},
            {{ var('value_age_cap') }}
        ) as capped_age
    from {{ ref('int_player_info') }} as player
    inner join {{ ref('stg_persons') }} as person
        on
            player.snapshot_date = person.snapshot_date
            and player.tid = person.tid
    left join {{ ref('int_teams') }} as teams
        on
            player.snapshot_date = teams.snapshot_date
            and player.club_tid = teams.team_tid
    left join {{ ref('int_team_leagues') }} as own_league
        on
            player.snapshot_date = own_league.snapshot_date
            and player.club_tid = own_league.team_tid
    left join {{ ref('int_team_leagues') }} as first_league
        on
            teams.snapshot_date = first_league.snapshot_date
            and teams.club_tid = first_league.team_tid
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
