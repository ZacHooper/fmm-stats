-- Each player whose origin club (dim_person: the youth system he came through,
-- an academy mapped to its parent) is placed in a home region
-- (int_club_regions.home_region_id), on each snapshot: that region, his age,
-- the tier his team plays in (NULL outside the home nation's men's leagues),
-- and level_tier, the highest scored tier whose level
-- (fact_tier_level_snapshot) he reaches: 1 is a Premier League regular's level
-- or better, NULL below the lowest scored tier's. The CA it is read from
-- stays here.
with origins as (
    select
        player.snapshot_date,
        player.person_id,
        person.origin_club_tid,
        regions.home_region_id,
        player.age,
        player.team_tid,
        player.ca
    from {{ ref('fact_player_snapshot') }} as player
    inner join {{ ref('dim_person') }} as person
        on player.person_id = person.person_id
    inner join {{ ref('int_club_regions') }} as regions
        on
            player.snapshot_date = regions.snapshot_date
            and person.origin_club_tid = regions.club_tid
    where regions.home_region_id is not null
),

levels as (
    select
        origins.snapshot_date,
        origins.person_id,
        min(tier_level.tier) as level_tier
    from origins
    inner join {{ ref('fact_tier_level_snapshot') }} as tier_level
        on
            origins.snapshot_date = tier_level.snapshot_date
            and tier_level.is_scored
            and origins.ca >= tier_level.level_ca
    group by origins.snapshot_date, origins.person_id
)

select
    origins.snapshot_date,
    origins.person_id,
    origins.origin_club_tid,
    origins.home_region_id,
    origins.age,
    origins.age < {{ var('region_u21_age') }} as is_under_21,
    origins.team_tid,
    tiers.tier,
    levels.level_tier
from origins
left join levels
    on
        origins.snapshot_date = levels.snapshot_date
        and origins.person_id = levels.person_id
left join {{ ref('int_home_team_tiers') }} as tiers
    on
        origins.snapshot_date = tiers.snapshot_date
        and origins.team_tid = tiers.team_tid
