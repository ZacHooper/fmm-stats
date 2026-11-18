-- Where each region's players play, on each snapshot: for every scored tier,
-- the players from the region's youth systems (fact_player_origin_snapshot)
-- playing for a team in that tier (the borrowing club's on a loan; a reserve
-- side does not count), all ages and under-21s. nation_share is the region's
-- part of the nation's count in that tier; nation_share_index is that share
-- over the region's on the first snapshot.
with regions as (
    select distinct
        snapshot_date,
        home_region_id
    from {{ ref('fact_player_origin_snapshot') }}
),

grid as (
    select
        regions.snapshot_date,
        regions.home_region_id,
        tier_level.tier,
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
        grid.home_region_id,
        grid.tier,
        grid.age_group,
        count(player.person_id) as n_players
    from grid
    left join {{ ref('fact_player_origin_snapshot') }} as player
        on
            grid.snapshot_date = player.snapshot_date
            and grid.home_region_id = player.home_region_id
            and grid.tier = player.tier
            and (grid.age_group = 'all' or player.is_under_21)
    group by all
),

shares as (
    select
        *,
        n_players / nullif(
            sum(n_players) over (
                partition by snapshot_date, tier, age_group
            ),
            0
        ) as nation_share
    from counts
)

select
    *,
    nation_share / nullif(
        first_value(nation_share) over (
            partition by home_region_id, tier, age_group
            order by snapshot_date
        ),
        0
    ) as nation_share_index
from shares
