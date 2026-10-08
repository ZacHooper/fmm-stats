-- Every position a player is listed at carries both Level %iles, each in
-- [0, 100], exactly when he has an ability to rank (a player with none has
-- neither). One row per player, snapshot and position that breaks it.
with levels as (
    select
        snapshot_date,
        person_id,
        ca is null as is_unranked,
        unnest(positions, recursive := true)
    from {{ ref('fact_player_snapshot') }}
)

select
    snapshot_date,
    person_id,
    position,
    is_unranked,
    level_league,
    level_global
from levels
where
    (level_league is null) <> is_unranked
    or (level_global is null) <> is_unranked
    or level_league not between 0 and 100
    or level_global not between 0 and 100
