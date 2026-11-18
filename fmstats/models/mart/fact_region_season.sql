-- Each region's appearances in the home nation's scored tiers, by season: every
-- appearance by a player from the region's youth systems for a team in a
-- scored tier that season, weighted by the tier's tier_weight. A finished
-- season is its career-history lines (fact_player_season); the season of the
-- latest snapshot adds the This Season panel's club_season line for the team
-- he is in now, which the history line for that club does not yet hold (the
-- larger of the two is kept). A team's tier for a season is its league on
-- the season's latest snapshot or, for the season before the first snapshot,
-- the league it finished in (last_league_cid). Weights are those of the
-- season's first snapshot, or the next season's where it has none.
-- nation_share is the region's part of the nation's weighted appearances
-- and nation_share_index that share over the region's in the first season.
with snapshots as (
    select
        snapshot_date,
        season
    from {{ ref('stg_snapshots') }}
),

season_last as (
    select
        season,
        max(snapshot_date) as snapshot_date
    from snapshots
    group by season
),

latest as (
    select max(snapshot_date) as snapshot_date from snapshots
),

team_tiers as (
    select
        season_last.season,
        tiers.team_tid,
        tiers.tier
    from season_last
    inner join {{ ref('int_home_team_tiers') }} as tiers
        on season_last.snapshot_date = tiers.snapshot_date
    union all
    select
        first_snapshot.season - 1 as season,
        team.team_tid,
        competition.level + 1 as tier
    from (
        select
            season,
            min(snapshot_date) as snapshot_date
        from snapshots
        where
            season
            = (
                select min(first_seasons.season) as first_season
                from snapshots as first_seasons
            )
        group by season
    ) as first_snapshot
    inner join {{ ref('int_team_snapshots') }} as team
        on first_snapshot.snapshot_date = team.snapshot_date
    inner join {{ ref('int_competitions') }} as competition
        on team.last_league_cid = competition.cid
    where
        competition.type = 'league'
        and not competition.is_women
        and competition.nation_id in (
            select tiers.nation_id
            from {{ ref('int_home_team_tiers') }} as tiers
        )
),

weights as (
    select
        seasons.season,
        tier_level.tier,
        tier_level.tier_weight
    from (select distinct season from team_tiers) as seasons
    inner join {{ ref('fact_tier_level_snapshot') }} as tier_level
        on tier_level.snapshot_date = (
            select min(snapshots.snapshot_date) as first_snapshot_date
            from snapshots
            where snapshots.season >= seasons.season
        )
    where tier_level.is_scored
),

origin as (
    select
        person_id,
        home_region_id
    from {{ ref('fact_player_origin_snapshot') }}
    qualify row_number() over (
        partition by person_id order by snapshot_date desc
    ) = 1
),

history as (
    select
        person_id,
        season,
        team_tid,
        sum(apps) as appearances
    from {{ ref('fact_player_season') }}
    where team_tid is not null
    group by person_id, season, team_tid
),

panel as (
    select
        stats.person_id,
        snapshots.season,
        player.team_tid,
        stats.appearances
    from {{ ref('fact_player_season_stats') }} as stats
    inner join latest on stats.snapshot_date = latest.snapshot_date
    inner join snapshots on stats.snapshot_date = snapshots.snapshot_date
    inner join {{ ref('fact_player_snapshot') }} as player
        on
            stats.snapshot_date = player.snapshot_date
            and stats.person_id = player.person_id
    where stats.block = 'club_season'
),

lines as (
    select
        person_id,
        season,
        team_tid,
        max(appearances) as appearances
    from (
        select * from history
        union all
        select * from panel
    ) as both_sources
    group by person_id, season, team_tid
),

by_tier as (
    select
        lines.season,
        origin.home_region_id,
        team_tiers.tier,
        sum(lines.appearances) as appearances,
        sum(lines.appearances * weights.tier_weight) as weighted_appearances
    from lines
    inner join origin on lines.person_id = origin.person_id
    inner join team_tiers
        on
            lines.season = team_tiers.season
            and lines.team_tid = team_tiers.team_tid
    inner join weights
        on
            team_tiers.season = weights.season
            and team_tiers.tier = weights.tier
    group by all
),

regions as (
    select
        season,
        home_region_id,
        sum(appearances) as appearances,
        sum(weighted_appearances) as weighted_appearances,
        list(
            { 'tier': tier, 'appearances': appearances }
            order by tier
        ) as appearances_by_tier
    from by_tier
    group by season, home_region_id
),

shares as (
    select
        *,
        weighted_appearances
        / sum(weighted_appearances) over (partition by season) as nation_share
    from regions
)

select
    season,
    home_region_id,
    season = (
        select snapshots.season from snapshots
        inner join latest on snapshots.snapshot_date = latest.snapshot_date
    ) as is_live,
    appearances,
    weighted_appearances,
    appearances_by_tier,
    nation_share,
    nation_share / nullif(
        first_value(nation_share) over (
            partition by home_region_id order by season
        ),
        0
    ) as nation_share_index
from shares
