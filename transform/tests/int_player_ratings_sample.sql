{#- 50 players at the newest snapshot, every method and role, recomputed by a different route
    (a sum over the attribute columns rather than the model's UNPIVOT): a row is returned for
    each rating that is missing or differs. A role a weight-set does not list is flat. -#}
{%- set s = rating_sample() -%}
{%- set keep = "season = " ~ s.season ~ " AND phase = '" ~ s.phase ~ "' AND tid IN ("
               ~ (s.tids | join(', ')) ~ ")" -%}
WITH combos AS (
    SELECT m.method, r.role
    FROM (SELECT DISTINCT method FROM {{ source('raw', 'role_weights') }}) m
    CROSS JOIN (SELECT DISTINCT role FROM {{ source('raw', 'position_role_map') }}) r
),
expected AS (
    SELECT a.season, a.phase, a.tid, c.method, c.role,
           {% for at in var('attr_order') -%}
           a."{{ at }}" * COALESCE((SELECT w.weight FROM {{ source('raw', 'role_weights') }} w
                                    WHERE w.method = c.method AND w.role = c.role
                                      AND w.attribute = '{{ at | lower }}'), 1)
           {{- ' +' if not loop.last }}
           {% endfor -%} AS rating
    FROM {{ ref('int_player_attributes') }} a CROSS JOIN combos c
    WHERE {{ keep }}
),
model AS (
    SELECT * FROM {{ ref('int_player_ratings') }} WHERE {{ keep }}
)
SELECT season, phase, tid, method, role, e.rating, m.rating AS model_rating
FROM expected e FULL JOIN model m USING (season, phase, tid, method, role)
WHERE e.rating IS NULL OR m.rating IS NULL OR abs(m.rating - e.rating) > 1e-9
UNION ALL   -- an empty sample would pass vacuously
SELECT NULL, NULL, NULL, 'empty sample', NULL, NULL, NULL
WHERE (SELECT count(DISTINCT tid) FROM expected) < 50
