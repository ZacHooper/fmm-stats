-- How each team's competition season ended: the stage and round reached, the
-- game's own final league position (a finished league season), its latest
-- table position in the stage it reached, and whether it won (NULL until the
-- save decides it).
select
    team_tid,
    cid,
    competition_season,
    stage_reached,
    round_reached,
    final_position,
    table_position,
    is_winner
from {{ ref('int_competition_outcomes') }}
