-- The transfer-value model's inputs for every player, one row per
-- (snapshot_date, tid): what int.player_value scores and
-- scripts/fit_value_model.py fits on. The model's league reputation is that of
-- the league his team plays in (int.team_leagues); a reserve side's is its
-- first team's, with is_reserve set. value is the value the save states, our
-- own squad's only (int.player_info.value).
-- Which league counts is a CASE over both joins, not a condition on the team
-- in either join's ON: a condition on the left side alone turns DuckDB's hash
-- join into a nested loop over every (player, team-league) pair.
{%- set reserve = var('team_types')[2] %}

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
    {{ age_on('person.dob', 'player.snapshot_date') }} as age,
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
