-- The competition each stage of the fixture list belongs to. The fixture names
-- its stage (stage_key, within a competition season) but no readable
-- competition (docs/TODO.md), so a stage is labelled from:
--   'our_match'   one of our own matches in it (its cid, from the match table);
--   'team_league' else its teams are exactly the teams of one league on the
--                 snapshot holding its fixtures (all of them, no other).
-- A stage neither labels (a cup abroad), and a fixture with no competition
-- season (a friendly), has no row.
with stage_matches as (
    select
        stage_key,
        competition_season,
        match_date,
        home_team_tid,
        away_team_tid,
        source_snapshot_date
    from {{ ref('int_world_matches') }}
    where competition_season is not null
),

from_ours as (
    select
        stage_side.stage_key,
        stage_side.competition_season,
        mode(ours.cid) as cid
    from stage_matches as stage_side
    inner join {{ ref('int_our_matches') }} as ours
        on
            stage_side.match_date = ours.match_date
            and stage_side.home_team_tid = ours.home_team_tid
            and stage_side.away_team_tid = ours.away_team_tid
    group by stage_side.stage_key, stage_side.competition_season
),

stage_teams as (
    select
        stage_key,
        competition_season,
        source_snapshot_date,
        home_team_tid as team_tid
    from stage_matches
    union
    select
        stage_key,
        competition_season,
        source_snapshot_date,
        away_team_tid as team_tid
    from stage_matches
),

stage_leagues as (
    select
        stage_side.stage_key,
        stage_side.competition_season,
        stage_side.source_snapshot_date,
        count(distinct stage_side.team_tid) as n_teams,
        count(distinct teams.league_cid) as n_leagues,
        count(teams.league_cid) as n_with_league,
        any_value(teams.league_cid) as league_cid
    from stage_teams as stage_side
    left join {{ ref('int_team_snapshots') }} as teams
        on
            stage_side.source_snapshot_date = teams.snapshot_date
            and stage_side.team_tid = teams.team_tid
    group by
        stage_side.stage_key,
        stage_side.competition_season,
        stage_side.source_snapshot_date
),

league_sizes as (
    select
        snapshot_date,
        league_cid,
        count(*) as n_teams
    from {{ ref('int_team_snapshots') }}
    where league_cid is not null
    group by snapshot_date, league_cid
),

from_leagues as (
    select
        stage_side.stage_key,
        stage_side.competition_season,
        any_value(stage_side.league_cid) as cid
    from stage_leagues as stage_side
    inner join league_sizes as sizes
        on
            stage_side.source_snapshot_date = sizes.snapshot_date
            and stage_side.league_cid = sizes.league_cid
    where
        stage_side.n_leagues = 1
        and stage_side.n_with_league = stage_side.n_teams
        and stage_side.n_teams = sizes.n_teams
    group by stage_side.stage_key, stage_side.competition_season
    having count(distinct stage_side.league_cid) = 1
)

select
    coalesce(ours.stage_key, leagues.stage_key) as stage_key,
    coalesce(ours.competition_season, leagues.competition_season)
        as competition_season,
    coalesce(ours.cid, leagues.cid) as cid,
    case
        when ours.cid is not null then 'our_match' else 'team_league'
    end as competition_source
from from_ours as ours
full outer join from_leagues as leagues
    on
        ours.stage_key = leagues.stage_key
        and ours.competition_season = leagues.competition_season
