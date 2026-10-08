-- Every table in mart_standings (a stage group after a matchday) numbers its
-- teams 1..n with no gap: the lowest position is 1 and the highest is the
-- number of teams. Uniqueness of team and position is a yml test.
select
    cid,
    competition_season,
    stage_index,
    stage_key,
    matchday,
    count(*) as teams,
    min(position) as first_position,
    max(position) as last_position
from {{ ref('mart_standings') }}
group by cid, competition_season, stage_index, stage_key, matchday
having min(position) <> 1 or max(position) <> count(*)
