-- Each tier of the home nation's men's leagues on each snapshot, and how good
-- it is: level_ca is the median CA of its teams' best var('region_regulars')
-- players (the team the player's squad listing resolves to), every
-- nationality counted. A tier is scored when its leagues have
-- matches in the store (the game plays out only the top of the pyramid).
-- tier_weight is the tier's level above the first unscored tier's (0 where
-- there is none), relative to the lowest scored tier's: the lowest scored tier
-- weighs 1. CA stays in the warehouse; only the weight and counts leave it.
with regulars as (
    select
        tiers.snapshot_date,
        tiers.tier,
        tiers.team_tid,
        player.ca,
        row_number() over (
            partition by tiers.snapshot_date, tiers.team_tid
            order by player.ca desc
        ) as squad_rank
    from {{ ref('int_home_team_tiers') }} as tiers
    inner join {{ ref('fact_player_snapshot') }} as player
        on
            tiers.snapshot_date = player.snapshot_date
            and tiers.team_tid = player.team_tid
    where player.ca is not null
),

played as (
    select distinct competition.level + 1 as tier
    from {{ ref('int_matches') }} as matches
    inner join {{ ref('int_competitions') }} as competition
        on matches.cid = competition.cid
    where
        competition.type = 'league'
        and not competition.is_women
        and competition.nation_id in (
            select tiers.nation_id
            from {{ ref('int_home_team_tiers') }} as tiers
        )
),

levels as (
    select
        regulars.snapshot_date,
        regulars.tier,
        count(distinct regulars.team_tid) as n_teams,
        median(regulars.ca) as level_ca,
        regulars.tier in (select played.tier from played) as is_scored
    from regulars
    where regulars.squad_rank <= {{ var('region_regulars') }}
    group by regulars.snapshot_date, regulars.tier
),

bounds as (
    select
        snapshot_date,
        min(level_ca) filter (where is_scored) as lowest_scored_ca,
        coalesce(
            max(level_ca) filter (
                where not is_scored
                and tier = (
                    select max(scored.tier) + 1 as first_unscored_tier
                    from levels as scored
                    where scored.is_scored
                )
            ),
            0
        ) as floor_ca
    from levels
    group by snapshot_date
)

select
    levels.snapshot_date,
    levels.tier,
    levels.n_teams,
    levels.level_ca,
    levels.is_scored,
    case
        when levels.is_scored
            then
                (levels.level_ca - bounds.floor_ca)
                / nullif(bounds.lowest_scored_ca - bounds.floor_ca, 0)
    end as tier_weight
from levels
inner join bounds on levels.snapshot_date = bounds.snapshot_date
