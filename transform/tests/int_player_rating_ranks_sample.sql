-- One slice (newest snapshot, first method, first role): one row per non-staff
-- player, percentiles spanning 0..100, and the best rating
-- ranked 1. Returns a row when any of those breaks.
{%- set s = rating_sample() %}
{%- set in_snapshot %}
    snapshot_date = '{{ s.snapshot_date }}'
{%- endset %}

with ranks as (
    select
        tid,
        rating,
        pctile,
        rank_overall
    from {{ ref('int_player_rating_ranks') }}
    where
        {{ in_snapshot }}
        and method = '{{ s.method }}'
        and role = '{{ s.role }}'
),

players as (
    select count(*) as players
    from {{ ref('int_player_attributes') }}
    where {{ in_snapshot }}
),

facts as (
    select
        count(*) as n,
        count(distinct tid) as tids,
        min(pctile) as lo,
        max(pctile) as hi,
        min(rank_overall) as top_rank,
        arg_max(rank_overall, rating) as best_rank
    from ranks
)

select
    facts.n,
    facts.tids,
    facts.lo,
    facts.hi,
    facts.top_rank,
    facts.best_rank,
    players.players
from facts
cross join players
where
    facts.n != players.players
    or facts.tids != facts.n
    or facts.lo != 0
    or facts.hi != 100
    or facts.top_rank != 1
    or facts.best_rank != 1
-- rating_sample() reads these:
-- depends_on: {{ ref('stg_snapshots') }} {{ ref('int_player_records') }}
-- depends_on: {{ ref('stg_role_weights') }} {{ ref('stg_position_roles') }}
