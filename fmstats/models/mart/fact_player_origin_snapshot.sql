-- Each player whose origin club (dim_person: the youth system he came through,
-- an academy mapped to its parent) is placed in a home region
-- (int_club_regions.home_region_id), on each snapshot, with two readings of
-- how far he has got:
--   where he plays: team_tid is the team he plays for, the borrowing club's
--     on a loan (is_on_loan), else his own first or B team, NULL when only a
--     reserve side lists him (mart_squad_membership); tier is that team's
--     tier, NULL outside the home nation's men's leagues.
--   how good he is: level_tier, the highest scored tier whose level
--     (fact_tier_level_snapshot) he reaches wherever he plays: 1 is at least
--     a top-flight typical regular's level, NULL below the lowest scored
--     tier's. The CA it is read from stays here.
with playing as (
    select
        snapshot_date,
        person_id,
        team_tid,
        is_loan_in as is_on_loan
    from {{ ref('mart_squad_membership') }}
    where team_type in ('first', 'b_team')
    qualify row_number() over (
        partition by snapshot_date, person_id
        order by is_loan_in desc, team_type = 'first' desc, team_tid
    ) = 1
),

origins as (
    select
        player.snapshot_date,
        player.person_id,
        person.origin_club_tid,
        regions.home_region_id,
        player.age,
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
    playing.team_tid,
    coalesce(playing.is_on_loan, false) as is_on_loan,
    tiers.tier,
    levels.level_tier
from origins
left join playing
    on
        origins.snapshot_date = playing.snapshot_date
        and origins.person_id = playing.person_id
left join levels
    on
        origins.snapshot_date = levels.snapshot_date
        and origins.person_id = levels.person_id
left join {{ ref('int_home_team_tiers') }} as tiers
    on
        origins.snapshot_date = tiers.snapshot_date
        and playing.team_tid = tiers.team_tid
