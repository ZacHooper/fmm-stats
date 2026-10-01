{#- rating = SUM(attribute * weight) per (method, role); an attribute a role does not list
    counts at weight 1. Derived from the 23 attributes only, so it carries no ability number.
    The web app computes the same ratings in the browser (site/js/data.js); a change to the
    formula has to land in both. -#}
WITH long AS (
    UNPIVOT {{ ref('int_player_attributes') }}
    ON {% for a in var('attr_order') %}"{{ a }}"{{ ', ' if not loop.last }}{% endfor %}
    INTO NAME attribute VALUE value
),
combos AS (
    -- Every method x every role, not only the pairs role_weights lists: a role with no rows
    -- there is FLAT (every attribute at weight 1), which scripts/derive_weight_set.py ships
    -- when no weighting beats a flat baseline. COALESCE(weight, 1) below gives its rating.
    SELECT m.method, r.role
    FROM (SELECT DISTINCT method FROM {{ source('raw', 'role_weights') }}) m
    CROSS JOIN (SELECT DISTINCT role FROM {{ source('raw', 'position_role_map') }}) r
)
SELECT l.season, l.phase, l.tid, c.method, c.role,
       SUM(l.value * COALESCE(w.weight, 1)) AS rating
FROM long l
CROSS JOIN combos c
LEFT JOIN {{ source('raw', 'role_weights') }} w
  ON w.method = c.method AND w.role = c.role AND w.attribute = LOWER(l.attribute)
GROUP BY l.season, l.phase, l.tid, c.method, c.role
