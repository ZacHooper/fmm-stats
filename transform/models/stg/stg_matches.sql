-- Our own matches, one row per match with detail. anchor is the match row's
-- offset in the save, its key. is_home says the managed side played at home.
-- star_home / star_away and player_of_match are person tids.
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
    {{ side }}_interceptions{% if not loop.last %},{% endif %}
    {% endfor %}
from {{ source('raw', 'matches') }}
