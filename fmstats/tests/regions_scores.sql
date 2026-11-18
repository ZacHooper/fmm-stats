-- The regional strength models hold together:
--   weights not descending   a scored tier weighs more than the tier below it,
--                            and the lowest scored tier weighs 1
--   elo not zero-sum         a rated match moves its two sides by equal and
--                            opposite amounts
--   elo not chained          each match row starts from the team's previous
--                            rating
--   share not whole          a measure's regional shares sum to 1 across the
--                            nation (where the nation has any)
with weights as (
    select
        snapshot_date,
        tier,
        tier_weight,
        lead(tier_weight) over (
            partition by snapshot_date order by tier
        ) as next_weight,
        max(tier) over (partition by snapshot_date) as lowest_tier
    from {{ ref('fact_tier_level_snapshot') }}
    where is_scored
),

moves as (
    select
        match_id,
        sum(elo - elo_before) as net_change
    from {{ ref('fact_club_elo') }}
    where rating_event = 'match'
    group by match_id
),

chain as (
    select
        team_tid,
        event_order,
        elo_before,
        lag(elo) over (
            partition by team_tid order by event_order
        ) as previous_elo
    from {{ ref('fact_club_elo') }}
),

level_shares as (
    select
        snapshot_date,
        level_tier,
        age_group,
        sum(nation_share) as total_share
    from {{ ref('fact_region_level_snapshot') }}
    group by all
    having sum(n_players) > 0
),

season_shares as (
    select
        season,
        sum(nation_share) as total_share
    from {{ ref('fact_region_season') }}
    group by season
)

select
    'weights not descending' as "check",
    snapshot_date::varchar || ' tier ' || tier::varchar as subject
from weights
where
    tier_weight <= next_weight
    or (tier = lowest_tier and abs(tier_weight - 1) > 1e-9)
union all
select
    'elo not zero-sum' as "check",
    match_id::varchar as subject
from moves
where abs(net_change) > 1e-6
union all
select
    'elo not chained' as "check",
    team_tid::varchar || ' #' || event_order::varchar as subject
from chain
where event_order > 0 and abs(elo_before - previous_elo) > 1e-6
union all
select
    'share not whole' as "check",
    snapshot_date::varchar || ' ' || level_tier::varchar || ' ' || age_group
        as subject
from level_shares
where abs(total_share - 1) > 1e-6
union all
select
    'share not whole' as "check",
    season::varchar as subject
from season_shares
where abs(total_share - 1) > 1e-6
