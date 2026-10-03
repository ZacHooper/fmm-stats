-- mart.player_primary_position on the new layers: a player's primary position
-- on each snapshot, the one he is most familiar with, then the one he is best
-- at (Level %ile in his league), then alphabetical.
select
    season,
    phase,
    snap_ix,
    tid,
    person_id,
    name,
    club_tid,
    club,
    league_cid,
    position,
    role,
    familiarity,
    level_league,
    level_nation,
    level_global
from {{ ref('site_player_position_levels') }}
qualify
    row_number() over (
        partition by season, phase, tid
        order by familiarity desc, level_league desc nulls last, position asc
    ) = 1
