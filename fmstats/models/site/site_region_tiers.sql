-- The home nation's league tiers on each snapshot, for the Regions tab's key:
-- each tier's leagues, whether it is scored and its weight in the appearance
-- score. The level behind the weight (fact_tier_level_snapshot.level_ca) is
-- raw ability and stays in the mart.
with leagues as (
    select
        tiers.snapshot_date,
        tiers.tier,
        list(
            distinct competition.name order by competition.name
        ) as league_names
    from {{ ref('int_home_team_tiers') }} as tiers
    inner join {{ ref('dim_competition') }} as competition
        on tiers.league_cid = competition.cid
    group by tiers.snapshot_date, tiers.tier
)

select
    levels.snapshot_date,
    levels.tier,
    levels.n_teams,
    levels.is_scored,
    levels.tier_weight,
    leagues.league_names
from {{ ref('fact_tier_level_snapshot') }} as levels
left join leagues
    on
        levels.snapshot_date = leagues.snapshot_date
        and levels.tier = leagues.tier
