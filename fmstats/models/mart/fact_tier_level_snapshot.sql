-- Each tier of the home nation's men's leagues on each snapshot, and how good
-- it is. A tier is scored when its leagues have matches in the store (the game
-- plays out only the top of the pyramid). A scored tier's level_ca is the
-- median CA of its teams' best var('region_regulars') players (the team the
-- player's squad listing resolves to), every nationality counted.
--
-- Below the scored tiers the save holds few or no players for most clubs, so
-- a measured level would come from the handful with a squad. Instead an
-- unscored tier's level is extrapolated (is_level_estimated): the scored
-- tiers' levels fall by a near-constant ratio per tier, so the line through
-- ln(level_ca) against tier is carried on down.
--
-- tier_weight is a scored tier's level above that extrapolated line's level
-- one tier below the lowest scored tier, relative to the lowest scored tier's:
-- the lowest scored tier weighs 1. CA stays in the warehouse; only the weight
-- and counts leave it.
with regulars as (
    select
        tiers.snapshot_date,
        tiers.tier,
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

tiers as (
    select
        snapshot_date,
        tier,
        count(*) as n_teams,
        tier in (select played.tier from played) as is_scored
    from {{ ref('int_home_team_tiers') }}
    group by snapshot_date, tier
),

measured as (
    select
        snapshot_date,
        tier,
        median(ca) as level_ca
    from regulars
    where squad_rank <= {{ var('region_regulars') }}
    group by snapshot_date, tier
),

fit as (
    select
        tiers.snapshot_date,
        regr_slope(ln(measured.level_ca), tiers.tier) as slope,
        regr_intercept(ln(measured.level_ca), tiers.tier) as intercept,
        max(tiers.tier) as lowest_scored_tier,
        arg_max(measured.level_ca, tiers.tier) as lowest_scored_ca
    from tiers
    inner join measured
        on
            tiers.snapshot_date = measured.snapshot_date
            and tiers.tier = measured.tier
    where tiers.is_scored
    group by tiers.snapshot_date
),

levels as (
    select
        tiers.snapshot_date,
        tiers.tier,
        tiers.n_teams,
        tiers.is_scored,
        not tiers.is_scored as is_level_estimated,
        case
            when tiers.is_scored then measured.level_ca
            else exp(fit.intercept + fit.slope * tiers.tier)
        end as level_ca,
        fit.lowest_scored_ca,
        exp(fit.intercept + fit.slope * (fit.lowest_scored_tier + 1))
            as floor_ca
    from tiers
    left join measured
        on
            tiers.snapshot_date = measured.snapshot_date
            and tiers.tier = measured.tier
    left join fit on tiers.snapshot_date = fit.snapshot_date
)

select
    snapshot_date,
    tier,
    n_teams,
    level_ca,
    is_level_estimated,
    is_scored,
    case
        when is_scored
            then
                (level_ca - floor_ca)
                / nullif(lowest_scored_ca - floor_ca, 0)
    end as tier_weight
from levels
