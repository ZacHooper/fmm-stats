-- The This Season panel per person: the panel's row is keyed by the player's
-- attribute record (sid), which his person record names on the same snapshot.
-- average_rating is the screen's Av R: the rating total over appearances,
-- truncated to two places. A handful of attribute records per save have no
-- person record (a freed slot); their rows are dropped here. season is the
-- career's season of the snapshot (stg_snapshots).
select
    stats.snapshot_date,
    snapshots.season,
    people.person_id,
    person.tid,
    stats.block,
    stats.appearances,
    stats.goals,
    stats.assists,
    stats.goals_conceded,
    stats.rating_total,
    trunc(100.0 * stats.rating_total / nullif(stats.appearances, 0))
    / 100 as average_rating,
    stats.yellows,
    stats.reds,
    stats.player_of_match_awards
from {{ ref('stg_player_season_stats') }} as stats
inner join {{ ref('stg_snapshots') }} as snapshots
    on stats.snapshot_date = snapshots.snapshot_date
inner join {{ ref('stg_persons') }} as person
    on
        stats.snapshot_date = person.snapshot_date
        and stats.sid = person.sid
inner join {{ ref('int_person_snapshots') }} as people
    on
        person.snapshot_date = people.snapshot_date
        and person.tid = people.tid
