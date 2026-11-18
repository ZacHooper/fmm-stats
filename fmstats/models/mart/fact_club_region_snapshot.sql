-- Each team in the home nation's men's leagues on each snapshot: its region
-- (its ground's, grouped as int_club_regions.home_region_id), its tier, its
-- Elo rating as of that day (the last rating event on or before it,
-- fact_club_elo) and its facilities and reputation.
-- The unit the regional club scores (fact_region_snapshot) aggregate.
select
    tiers.snapshot_date,
    tiers.team_tid,
    tiers.club_tid,
    regions.home_region_id,
    tiers.tier,
    levels.is_scored,
    elo.elo,
    team.reputation,
    team.status,
    team.training_facilities,
    team.youth_facilities
from {{ ref('int_home_team_tiers') }} as tiers
inner join {{ ref('int_team_snapshots') }} as team
    on
        tiers.snapshot_date = team.snapshot_date
        and tiers.team_tid = team.team_tid
left join {{ ref('int_club_regions') }} as regions
    on
        tiers.snapshot_date = regions.snapshot_date
        and tiers.club_tid = regions.club_tid
left join {{ ref('fact_tier_level_snapshot') }} as levels
    on
        tiers.snapshot_date = levels.snapshot_date
        and tiers.tier = levels.tier
left join {{ ref('fact_club_elo') }} as elo
    on
        tiers.team_tid = elo.team_tid
        and tiers.snapshot_date >= elo.rating_date
qualify
    row_number() over (
        partition by tiers.snapshot_date, tiers.team_tid
        order by elo.event_order desc nulls last
    ) = 1
