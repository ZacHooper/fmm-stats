"""Role ratings: every player rated in every role of every weight-set.

  int.player_ratings       rating = SUM(attribute * weight) per (method, role); an attribute a
                           role does not list counts at weight 1. Derived from the 23
                           attributes only, so it carries no ability number.
  int.player_rating_ranks  each rating's percentile and rank among everyone at that snapshot

The web app computes the same ratings in the browser (`site/js/data.js`); a change to the
formula has to land in both.
"""
from .. import contract as C
from . import Model

_UNPIVOT = ", ".join(f'"{a}"' for a in C.ATTR_ORDER)

MODELS = [
    Model("int.player_ratings", f"""
WITH long AS (
    UNPIVOT int.player_attributes ON {_UNPIVOT} INTO NAME attribute VALUE value
),
combos AS (
    -- Every method x every role, not only the pairs role_weights lists: a role with no rows
    -- there is FLAT (every attribute at weight 1), which scripts/derive_weight_set.py ships
    -- when no weighting beats a flat baseline. COALESCE(weight, 1) below gives its rating.
    SELECT m.method, r.role
    FROM (SELECT DISTINCT method FROM raw.role_weights) m
    CROSS JOIN (SELECT DISTINCT role FROM raw.position_role_map) r
)
SELECT l.season, l.phase, l.tid, c.method, c.role,
       SUM(l.value * COALESCE(w.weight, 1)) AS rating
FROM long l
CROSS JOIN combos c
LEFT JOIN raw.role_weights w
  ON w.method = c.method AND w.role = c.role AND w.attribute = LOWER(l.attribute)
GROUP BY l.season, l.phase, l.tid, c.method, c.role""",
          grain=("season", "phase", "tid", "method", "role"),
          upstream=("int.player_attributes",),
          fks={"season, phase, tid": "int.players(season, phase, tid)"}),
    Model("int.player_rating_ranks", """
SELECT r.season, r.phase, r.method, r.role, r.tid, r.rating,
       p.name, p.club, p.club_tid,
       -- the club record's league: league_id, unless the club plays in another division
       CASE WHEN d.other_division = 65535 AND d.league_id NOT IN (0, 65535)
            THEN d.league_id END AS league_cid,
       ROUND(100 * PERCENT_RANK() OVER (
           PARTITION BY r.season, r.phase, r.method, r.role
           ORDER BY r.rating), 1) AS pctile,
       RANK() OVER (
           PARTITION BY r.season, r.phase, r.method, r.role
           ORDER BY r.rating DESC) AS rank_overall
FROM int.player_ratings r
JOIN int.players p USING (season, phase, tid)
LEFT JOIN raw.club_details d
       ON (d.season, d.phase, d.tid) = (p.season, p.phase, p.club_tid)
WHERE NOT p.is_staff""",
          grain=("season", "phase", "tid", "method", "role"),
          upstream=("int.player_ratings", "int.players")),
]
