-- The transfer-value model's inputs for every player, one row per
-- (snapshot_date, tid): his raw inputs, then one column per model term
-- (var('value_terms')), which int.player_value scores and
-- int.player_value_labels pairs with the save's stated values for
-- scripts/fit_value_model.py. A term is NULL where its input is missing or not
-- positive (a log of 0), and such a player gets no estimate.
-- The model's league reputation is that of the league his team plays in
-- (int.team_leagues); a reserve side's is its first team's, with is_reserve
-- set. value is the value the save states, our own squad's only
-- (int.player_info.value).
-- Which league counts is a CASE over both joins, not a condition on the team
-- in either join's ON: a condition on the left side alone turns DuckDB's hash
-- join into a nested loop over every (player, team-league) pair.
{%- set reserve = var('team_types')[2] %}

with inputs as (
    select
        player.snapshot_date,
        player.tid,
        player.person_id,
        player.ca,
        player.pa,
        player.reputation,
        player.current_reputation,
        player.world_reputation,
        case
            when teams.team_type = '{{ reserve }}'
                then first_league.league_reputation
            else own_league.league_reputation
        end as league_reputation,
        player.is_goalkeeper,
        coalesce(teams.team_type = '{{ reserve }}', false) as is_reserve,
        {{ age_on('person.dob', 'player.snapshot_date') }} as age,
        player.wage_gbp,
        player.contract_expiry,
        player.value
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

logs as (
    select
        *,
        case when reputation > 0 then ln(reputation) end as lrep,
        case
            when league_reputation > 0 then ln(league_reputation)
        end as llrp,
        ln(greatest(current_reputation, 1)) as lcrep,
        ln(greatest(world_reputation, 1)) as lwrep,
        ln(greatest(wage_gbp, 1)) as lwage
    from inputs
)

-- The terms, in var('value_terms') order: ability, the reputation trio and
-- the league's, goalkeeper and reserve flags, age as a quadratic with a hinge
-- past var('value_age_hinge'), wage, contract years left (capped at
-- var('value_contract_years_cap')), and four interactions: ability and
-- reputation with the league's reputation, the potential still to come for a
-- player under var('value_youth_age'), and wage with the league's reputation.
select
    snapshot_date,
    tid,
    person_id,
    ca,
    pa,
    reputation,
    current_reputation,
    world_reputation,
    league_reputation,
    is_goalkeeper,
    is_reserve,
    age,
    wage_gbp,
    contract_expiry,
    value,
    lrep,
    llrp,
    cast(is_goalkeeper as int) as gk,
    cast(is_reserve as int) as res,
    age * age as age2,
    greatest(age - {{ var('value_age_hinge') }}, 0) as age_over,
    lcrep,
    lwrep,
    lwage,
    least(
        greatest(date_diff('day', snapshot_date, contract_expiry) / 365.25, 0),
        {{ var('value_contract_years_cap') }}
    ) as yrs_left,
    ca * llrp as ca_llrp,
    lrep * llrp as lrep_llrp,
    (pa - ca) * greatest({{ var('value_youth_age') }} - age, 0) as pagap_young,
    lwage * llrp as wage_llrp
from logs
