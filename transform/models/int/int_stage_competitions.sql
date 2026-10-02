-- The competition each stage of the fixture list belongs to. The fixture names
-- its stage (stage_key, within a competition season) but no readable
-- competition (docs/TODO.md), so a stage is labelled from:
--   'our_match'        one of our own matches in it (the match table's cid);
--   'league_structure' else the league rule of mart.league_tables: a league's
--                      regular stage is a stage at stage_index 0 whose
--                      stage_key has fixtures on more than one matchday in
--                      some season (a league keeps its stage_key from season
--                      to season, so a season one matchday old counts too);
--                      a split league's championship
--                      and relegation groups are the season's other such
--                      stages whose every club, home and away, is one of its
--                      clubs. The league is the one most of its clubs belong
--                      to on the season's last snapshot (the snapshot of
--                      season competition_season + 1), and the stage's clubs
--                      with a league must number at least
--                      var('league_min_share') of that league's, which keeps
--                      a cup group out. They are counted whatever league they
--                      are in: a snapshot after the last matchday already
--                      has the promoted and relegated clubs in their new
--                      leagues.
-- This is a heuristic. The tables it gives (int_standings) match the game's
-- final positions for every complete Danish, English and German league in the
-- gate stores; Spain's differ only where teams are level on points, which
-- Spain breaks by head to head (docs/TODO.md #13). A stage neither labels (a
-- cup abroad), and a fixture with no competition season (a friendly), has no
-- row.
with fixtures as (
    select
        stage_key,
        competition_season,
        stage_index,
        subr,
        matchday,
        match_date,
        home_team_tid,
        away_team_tid
    from {{ ref('int_world_matches') }}
    where competition_season is not null
),

from_ours as (
    select
        fixtures.stage_key,
        fixtures.competition_season,
        mode(ours.cid) as cid
    from fixtures
    inner join {{ ref('int_our_matches') }} as ours
        on
            fixtures.match_date = ours.match_date
            and fixtures.home_team_tid = ours.home_team_tid
            and fixtures.away_team_tid = ours.away_team_tid
    group by fixtures.stage_key, fixtures.competition_season
),

season_matchdays as (
    select
        competition_season,
        stage_key,
        count(distinct matchday) as n_matchdays
    from fixtures
    group by competition_season, stage_key
),

multi_round as (
    select
        competition_season,
        stage_key,
        min(stage_index) as stage_index
    from fixtures
    where
        stage_key in (
            select season_matchdays.stage_key
            from season_matchdays
            where season_matchdays.n_matchdays > 1
        )
    group by competition_season, stage_key
),

sides as (
    select
        fixtures.competition_season,
        fixtures.stage_key,
        fixtures.home_team_tid as team_tid,
        fixtures.away_team_tid as opponent_tid
    from fixtures
    inner join multi_round
        on
            fixtures.competition_season = multi_round.competition_season
            and fixtures.stage_key = multi_round.stage_key
),

base_members as (
    select distinct
        sides.competition_season,
        sides.stage_key as league_key,
        unnest([sides.team_tid, sides.opponent_tid]) as team_tid
    from sides
    inner join multi_round
        on
            sides.competition_season = multi_round.competition_season
            and sides.stage_key = multi_round.stage_key
    where multi_round.stage_index = 0
),

bases as (
    select distinct
        competition_season,
        league_key
    from base_members
),

attached as (
    select
        sides.competition_season,
        bases.league_key,
        sides.stage_key
    from sides
    inner join bases
        on sides.competition_season = bases.competition_season
    left join base_members as home_member
        on
            bases.competition_season = home_member.competition_season
            and bases.league_key = home_member.league_key
            and sides.team_tid = home_member.team_tid
    left join base_members as away_member
        on
            bases.competition_season = away_member.competition_season
            and bases.league_key = away_member.league_key
            and sides.opponent_tid = away_member.team_tid
    group by sides.competition_season, bases.league_key, sides.stage_key
    having
        bool_and(
            home_member.team_tid is not null
            and away_member.team_tid is not null
        )
),

season_snapshot as (
    select
        season - 1 as competition_season,
        max(snapshot_date) as snapshot_date
    from {{ ref('stg_snapshots') }}
    group by season
),

member_leagues as (
    select
        members.competition_season,
        members.league_key,
        teams.league_cid,
        sum(count(*)) over (
            partition by members.competition_season, members.league_key
        ) as n_teams
    from base_members as members
    inner join season_snapshot
        on members.competition_season = season_snapshot.competition_season
    inner join {{ ref('int_team_snapshots') }} as teams
        on
            season_snapshot.snapshot_date = teams.snapshot_date
            and members.team_tid = teams.team_tid
    where teams.league_cid is not null
    group by members.competition_season, members.league_key, teams.league_cid
    qualify
        row_number() over (
            partition by members.competition_season, members.league_key
            order by count(*) desc, teams.league_cid asc
        ) = 1
),

league_sizes as (
    select
        season_snapshot.competition_season,
        teams.league_cid,
        count(*) as n_teams
    from season_snapshot
    inner join {{ ref('int_team_snapshots') }} as teams
        on season_snapshot.snapshot_date = teams.snapshot_date
    where teams.league_cid is not null
    group by season_snapshot.competition_season, teams.league_cid
),

leagues as (
    select
        member_leagues.competition_season,
        member_leagues.league_key,
        member_leagues.league_cid
    from member_leagues
    inner join league_sizes
        on
            member_leagues.competition_season = league_sizes.competition_season
            and member_leagues.league_cid = league_sizes.league_cid
    where
        member_leagues.n_teams
        >= {{ var('league_min_share') }} * league_sizes.n_teams
),

from_leagues as (
    select
        attached.stage_key,
        attached.competition_season,
        any_value(leagues.league_cid) as cid
    from attached
    inner join leagues
        on
            attached.competition_season = leagues.competition_season
            and attached.league_key = leagues.league_key
    group by attached.stage_key, attached.competition_season
    having count(distinct leagues.league_cid) = 1
)

select
    coalesce(ours.stage_key, leagues.stage_key) as stage_key,
    coalesce(ours.competition_season, leagues.competition_season)
        as competition_season,
    coalesce(ours.cid, leagues.cid) as cid,
    case
        when ours.cid is not null then 'our_match' else 'league_structure'
    end as competition_source
from from_ours as ours
full outer join from_leagues as leagues
    on
        ours.stage_key = leagues.stage_key
        and ours.competition_season = leagues.competition_season
