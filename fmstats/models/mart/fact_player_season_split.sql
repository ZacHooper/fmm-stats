-- Each player's season split by kind of competition, for every season a save
-- covers: the This Season panel as the season's last snapshot holds it
-- (through_date), one row per block with an appearance. The career history
-- (fact_player_season) holds every season's total, from before the first
-- save too, but not the split.
--
-- season is the career's (its rollover day). The panel clears at the end of
-- the player's own league's season, nation by nation, so for a league on
-- another calendar (Sweden, the USA) the panel can restart inside one of our
-- seasons: has_panel_reset marks a player whose club_season appearances fell
-- between two snapshots of the season, whose row then covers only the part
-- after the restart. is_live: the season is still being played, so its
-- figures grow with each save.
with snapshots as (
    select
        snapshot_date,
        season
    from {{ ref('stg_snapshots') }}
),

season_last as (
    select
        season,
        max(snapshot_date) as through_date
    from snapshots
    group by season
),

club_season as (
    select
        snapshots.season,
        snapshots.snapshot_date,
        players.person_id,
        coalesce(stats.appearances, 0) as appearances
    from snapshots
    inner join {{ ref('fact_player_snapshot') }} as players
        on snapshots.snapshot_date = players.snapshot_date
    left join {{ ref('fact_player_season_stats') }} as stats
        on
            players.snapshot_date = stats.snapshot_date
            and players.person_id = stats.person_id
            and stats.block = 'club_season'
),

resets as (
    select
        season,
        person_id,
        bool_or(appearances < previous_appearances) as has_panel_reset
    from (
        select
            season,
            person_id,
            appearances,
            lag(appearances) over (
                partition by season, person_id order by snapshot_date
            ) as previous_appearances
        from club_season
    ) as steps
    group by season, person_id
)

select
    stats.season,
    stats.person_id,
    stats.tid,
    stats.block,
    season_last.through_date,
    season_last.season = (
        select max(snapshots.season) as latest_season from snapshots
    ) as is_live,
    coalesce(resets.has_panel_reset, false) as has_panel_reset,
    stats.appearances,
    stats.goals,
    stats.assists,
    stats.goals_conceded,
    stats.rating_total,
    stats.average_rating,
    stats.yellows,
    stats.reds,
    stats.player_of_match_awards
from {{ ref('fact_player_season_stats') }} as stats
inner join season_last
    on
        stats.season = season_last.season
        and stats.snapshot_date = season_last.through_date
left join resets
    on
        stats.season = resets.season
        and stats.person_id = resets.person_id
