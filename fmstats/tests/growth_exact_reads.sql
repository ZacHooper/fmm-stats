-- An exact read of a player's attributes (attributes_are_estimated false)
-- comes only from our own squad: everyone outside the managed club's squad
-- arrays is on the model's estimates, and on every snapshot most of our squad
-- reads exact. A growth or forecast figure that filters on the flag relies on
-- both. One row per exact read outside our squad, and one per snapshot where
-- our exact reads are not a majority.
with snapshots as (
    select
        players.snapshot_date,
        players.person_id,
        players.attributes_are_estimated,
        exists (
            select 1
            from {{ ref('mart_squad_membership') }} as squads
            where
                squads.person_id = players.person_id
                and squads.snapshot_date = players.snapshot_date
                and squads.is_managed_club
        ) as in_our_squad
    from {{ ref('fact_player_snapshot') }} as players
    where players.has_attributes
)

select
    'exact outside our squad' as check_name,
    snapshot_date,
    person_id
from snapshots
where not in_our_squad and not attributes_are_estimated
union all
select
    'our squad mostly estimated' as check_name,
    snapshot_date,
    null as person_id
from snapshots
where in_our_squad
group by snapshot_date
having
    count(*) filter (where not attributes_are_estimated)
    <= count(*) filter (where attributes_are_estimated)
