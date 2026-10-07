-- Each player's career-history summary, one row per player per snapshot.
-- origin_club_tid is his youth or debut club, which may be an academy tid
-- (the u16 complement of its club's). Both club fields read NULL for "none"
-- (var('no_id16')).
select
    cast(phase as date) as snapshot_date,
    tid,
    nullif(origin_club_tid, {{ var('no_id16') }}) as origin_club_tid,
    nullif(last_season_club_tid, {{ var('no_id16') }}) as last_season_club_tid,
    record_offset,
    debut_end_year as debut_season
from {{ source('raw', 'player_history') }}
