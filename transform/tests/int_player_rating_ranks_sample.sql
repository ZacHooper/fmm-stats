{#- One slice (newest snapshot, first method, first role): one row per non-staff player with
    attributes, percentiles spanning 0..100, and the best rating ranked 1. Returns a row per
    broken expectation. -#}
{%- set s = rating_sample() -%}
{%- set snap = "season = " ~ s.season ~ " AND phase = '" ~ s.phase ~ "'" -%}
WITH ranks AS (
    SELECT * FROM {{ ref('int_player_rating_ranks') }}
    WHERE {{ snap }} AND method = '{{ s.method }}' AND role = '{{ s.role }}'
),
players AS (
    SELECT count(*) AS players FROM {{ ref('int_players') }}
    WHERE {{ snap }} AND has_attributes AND NOT is_staff
),
facts AS (
    SELECT count(*) AS n, count(DISTINCT tid) AS tids, min(pctile) AS lo, max(pctile) AS hi,
           min(rank_overall) AS top, arg_max(rank_overall, rating) AS best_rank
    FROM ranks
)
SELECT * FROM facts, players
WHERE n <> players OR tids <> n OR lo <> 0 OR hi <> 100 OR top <> 1 OR best_rank <> 1
