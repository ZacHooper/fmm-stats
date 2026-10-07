-- Each club's league history, one row per league season: the league, the
-- club's final position and how many clubs it had. The save stores the
-- season's start year; season is its end year, the project's season.
select
    cast(phase as date) as snapshot_date,
    club_tid,
    cid as league_cid,
    year + 1 as season,
    position,
    teams
from {{ source('raw', 'club_league_history') }}
