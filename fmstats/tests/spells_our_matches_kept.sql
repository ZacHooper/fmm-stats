-- The match table is emptied at the rollover and grows through a season, so
-- each of our matches is held by several snapshots. Every match any snapshot
-- holds is in dim_match once, as one of ours (has_detail): no snapshot's
-- matches are lost to a later snapshot's, and none is counted twice.
with stored as (
    select distinct
        match_date,
        home_team_tid,
        away_team_tid
    from {{ ref('stg_matches') }}
),

kept as (
    select
        match_date,
        home_team_tid,
        away_team_tid
    from {{ ref('dim_match') }}
    where has_detail
)

select
    'stored match missing from dim_match' as "check",  -- noqa: RF04
    stored.match_date,
    stored.home_team_tid,
    stored.away_team_tid
from stored
left join kept
    on
        stored.match_date = kept.match_date
        and stored.home_team_tid = kept.home_team_tid
        and stored.away_team_tid = kept.away_team_tid
where kept.match_date is null
union all
select
    'dim_match match no snapshot stores' as "check",  -- noqa: RF04
    kept.match_date,
    kept.home_team_tid,
    kept.away_team_tid
from kept
left join stored
    on
        kept.match_date = stored.match_date
        and kept.home_team_tid = stored.home_team_tid
        and kept.away_team_tid = stored.away_team_tid
where stored.match_date is null
