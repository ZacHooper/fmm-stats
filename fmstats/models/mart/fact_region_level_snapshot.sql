-- How many players each region has produced at each level, on each snapshot:
-- for every scored tier, the players from the region's youth systems
-- (fact_player_origin_snapshot) at that tier's level or better, all ages and
-- under-21s. nation_share is the region's part of the nation's count;
-- nation_share_index is that share over the region's on the first snapshot,
-- so 1.10 is a tenth more of the nation's players at that level than on day 1.
with regions as (
    select distinct
        snapshot_date,
        region_id
    from {{ ref('fact_player_origin_snapshot') }}
),

grid as (
    select
        regions.snapshot_date,
        regions.region_id,
        tier_level.tier as level_tier,
        age_group.age_group
    from regions
    inner join {{ ref('fact_tier_level_snapshot') }} as tier_level
        on regions.snapshot_date = tier_level.snapshot_date
    cross join (values ('all'), ('under_21')) as age_group (age_group)
    where tier_level.is_scored
),

counts as (
    select
        grid.snapshot_date,
        grid.region_id,
        grid.level_tier,
        grid.age_group,
        count(player.person_id) as n_players
    from grid
    left join {{ ref('fact_player_origin_snapshot') }} as player
        on
            grid.snapshot_date = player.snapshot_date
            and grid.region_id = player.region_id
            and grid.level_tier >= player.level_tier
            and (grid.age_group = 'all' or player.is_under_21)
    group by all
),

shares as (
    select
        *,
        n_players / nullif(
            sum(n_players) over (
                partition by snapshot_date, level_tier, age_group
            ),
            0
        ) as nation_share
    from counts
)

select
    *,
    nation_share / nullif(
        first_value(nation_share) over (
            partition by region_id, level_tier, age_group
            order by snapshot_date
        ),
        0
    ) as nation_share_index
from shares
