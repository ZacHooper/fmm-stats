-- Each player's place in a World Best XI pool, keyed (award_id, person_id,
-- entry_date), with the scrapbook entry that earned it: his profile as of
-- entry_date (club, competition, apps, goals, assists, average rating).
-- world_best_xi: each season's pool (var('world_best_xi_lists'), one list per
-- season) as the latest snapshot holding it has it; a pool fills and changes
-- while its season is played, and is_final marks one whose season has ended.
-- world_best_xi_all_time: the newest snapshot's All-Time pool
-- (var('world_best_xi_all_time_list')), each entry the season's entry it was
-- copied from (season NULL where no list held holds it, as for an entry
-- from before the career). person_id: an entry holds the player's tid, not
-- his person, and the game hands a retired player's tid to a newgen; so it is
-- the person with that tid whose date of birth gives the entry's age on its
-- date. The stored age can lag a birthday by a day or two (an entry dated the
-- 1st after a birthday on the 30th), so the age then may be one more; two
-- holders of one tid are decades apart.
{%- set seasonal = var('world_best_xi_lists') %}
{%- set awards = var('awards').keys() | list %}

with entries as (
    select
        scrapbook.*,
        coalesce(
            nullif(scrapbook.list_season, {{ var('no_id16') }}),
            snapshots.season
        ) as season,
        scrapbook.list_season = {{ var('no_id16') }} as is_in_progress
    from {{ ref('stg_scrapbook_entries') }} as scrapbook
    inner join {{ ref('stg_snapshots') }} as snapshots
        on scrapbook.snapshot_date = snapshots.snapshot_date
),

newest as (
    select max(snapshot_date) as snapshot_date
    from entries
),

seasonal as (
    select *
    from entries
    where list between {{ seasonal[0] }} and {{ seasonal[1] }}
    qualify snapshot_date = max(snapshot_date) over (partition by season)
),

all_time as (
    select
        pool.* exclude (season),  -- noqa: RF02
        copied.season
    from entries as pool
    inner join newest
        on pool.snapshot_date = newest.snapshot_date
    left join entries as copied
        on
            pool.snapshot_date = copied.snapshot_date
            and pool.player_tid = copied.player_tid
            and pool.entry_date = copied.entry_date
            and copied.list between {{ seasonal[0] }} and {{ seasonal[1] }}
    where pool.list = {{ var('world_best_xi_all_time_list') }}
),

pools as (
    select
        '{{ awards[0] }}' as award_id,
        season,
        not is_in_progress as is_final,
        * exclude (season, is_in_progress)
    from seasonal
    union all
    select
        '{{ awards[1] }}' as award_id,
        season,
        true as is_final,
        * exclude (season, is_in_progress)
    from all_time
)

select
    pools.award_id,
    pools.season,
    persons.person_id,
    pools.player_tid,
    pools.full_name as entry_name,
    pools.is_final,
    pools.entry_date,
    pools.club_tid,
    pools.loan_club_tid,
    pools.competition,
    pools.age,
    pools.apps,
    pools.goals,
    pools.assists,
    pools.avg_rating
from pools
left join {{ ref('int_persons') }} as persons
    on
        pools.player_tid = persons.tid
        and {{ age_on('persons.dob', 'pools.entry_date') }} - pools.age
        between 0 and 1
