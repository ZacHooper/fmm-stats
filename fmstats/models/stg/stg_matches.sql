-- Our own matches, one row per match with detail. anchor is the match row's
-- offset in the save, its key. is_home says the managed side played at home.
-- star_home / star_away and player_of_match are person tids. corners,
-- clear_cut_chances and offsides are each side's counts as the team head
-- stores them. fouls and manager_tid (the side's manager, a staff tid) are
-- FMM27's and NULL on an FMM22 match.
{%- set no_id32 = var('no_id32') %}
select
    cast(phase as date) as snapshot_date,
    anchor,
    date as match_date,
    competition,
    comp_id as cid,
    home_flag = 1 as is_home,
    home_tid as home_team_tid,
    away_tid as away_team_tid,
    attendance,
    score_home,
    score_away,
    star_home,
    star_away,
    formation,
    player_of_match,
    {% for side in ['home', 'away'] %}
    {{ side }}_shots,
    {{ side }}_shots_on_target,
    {{ side }}_rating,
    {{ side }}_players_used,
    {{ side }}_passes,
    {{ side }}_passes_completed,
    {{ side }}_tackles,
    {{ side }}_tackles_won,
    {{ side }}_crosses,
    {{ side }}_interceptions,
    {{ side }}_corners,
    {{ side }}_clear_cut_chances,
    {{ side }}_offsides,
    {{ side }}_fouls,
    nullif({{ side }}_manager_tid, {{ no_id32 }}) as {{ side }}_manager_tid
    {%- if not loop.last %},{% endif %}
    {% endfor %}
from {{ source('raw', 'matches') }}
