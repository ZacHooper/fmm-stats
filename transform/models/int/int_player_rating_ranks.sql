{#- each rating's percentile and rank among everyone at that snapshot -#}
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
FROM {{ ref('int_player_ratings') }} r
JOIN {{ ref('int_players') }} p USING (season, phase, tid)
LEFT JOIN {{ source('raw', 'club_details') }} d
       ON (d.season, d.phase, d.tid) = (p.season, p.phase, p.club_tid)
WHERE NOT p.is_staff
