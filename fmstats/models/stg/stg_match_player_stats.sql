-- Each player's line in our own matches, both sides. A minute or condition
-- the player has none of reads NULL (var('no_id8')): sub_on_minute is NULL for
-- a starter or an unused substitute, sub_off_minute for a player not taken
-- off. position is a starter's place in our own XI, NULL for the opposition
-- and for substitutes, in the positions' codes (var('match_position_codes')).
select
    cast(phase as date) as snapshot_date,
    anchor,
    side,
    tid as player_tid,
    team_tid,
    opponent_tid,
    date as match_date,
    competition,
    pos_order,
    rating,
    goals,
    assists,
    passa as passes,
    passc as passes_completed,
    keypass as key_passes,
    tacka as tackles,
    tackw as tackles_won,
    intercept as interceptions,
    heada as headers,
    headw as headers_won,
    crossa as crosses,
    crossc as crosses_completed,
    dribbles,
    mistakes,
    mistgoal as mistakes_to_goal,
    shota as shots,
    shoto as shots_on_target,
    nullif(condition, {{ var('no_id8') }}) as condition,
    nullif(subon, {{ var('no_id8') }}) as sub_on_minute,
    nullif(suboff, {{ var('no_id8') }}) as sub_off_minute,
    yellow as yellows,
    case position
        {% for code, position in var('match_position_codes').items() %}
        when '{{ code }}' then '{{ position }}'
        {% endfor %}
        else position
    end as position
from {{ source('raw', 'match_player_stats') }}
