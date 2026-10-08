-- site_players.development, the only form potential leaves the store in, is
-- one of the var('site_development_bands') words for every player with a
-- potential and NULL for one without, and every band occurs: a finer value
-- would leak ability. One row per offending player and snapshot, plus one per
-- band that never occurs.
with bands as (
    select bands.word
    from (
        values
        {% for floor, word in var('site_development_bands') %}
        ('{{ word }}'){% if not loop.last %},{% endif %}
        {% endfor %}
    ) as bands (word)
),

players as (
    select
        snapshots.snapshot_date,
        snapshots.person_id,
        snapshots.pa is not null as has_potential,
        site.development
    from {{ ref('site_players') }} as site
    inner join {{ ref('fact_player_snapshot') }} as snapshots
        on
            site.snapshot_date = snapshots.snapshot_date
            and site.person_id = snapshots.person_id
)

select
    'not a band' as check_name,
    players.snapshot_date,
    players.person_id,
    players.development
from players
where
    (players.development is null) = players.has_potential
    or players.development not in (select bands.word from bands)
union all
select
    'band never occurs' as check_name,
    null as snapshot_date,
    null as person_id,
    bands.word as development
from bands
where not exists (
    select 1 as found
    from players
    where players.development = bands.word
)
