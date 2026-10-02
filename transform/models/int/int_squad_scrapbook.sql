{%- set entry_cols = column_names(source('raw', 'player_scrapbook'))
       | reject('in', ['season', 'phase', 'player_tid']) | list -%}
{%- set lists = var('club_lists') -%}
WITH managed AS (
    SELECT CAST(value AS INTEGER) AS club_tid FROM {{ source('raw', 'app_config') }}
    WHERE key = 'career_managed_tid'
),
ours AS (
    SELECT e.season, e.phase, m.club_tid, 0 AS reserve
    FROM {{ source('raw', 'extracts') }} e CROSS JOIN managed m
    UNION ALL
    SELECT d.season, d.phase, d.tid, 1
    FROM {{ source('raw', 'club_details') }} d JOIN managed m ON d.main_club_tid = m.club_tid
),
squad AS (
    SELECT q.season, q.phase, q.player_tid AS tid,
           arg_min(q.club_tid, o.reserve) AS squad_club_tid
    FROM {{ source('raw', 'club_squad') }} q JOIN ours o USING (season, phase, club_tid)
    GROUP BY q.season, q.phase, q.player_tid
),
latest AS (
    SELECT * FROM {{ source('raw', 'player_scrapbook') }}
    WHERE list BETWEEN {{ lists[0] }} AND {{ lists[1] }}
    QUALIFY row_number() OVER (PARTITION BY season, phase, player_tid
                               ORDER BY scrapbook_date DESC, list DESC) = 1
)
SELECT q.season, q.phase, q.tid, q.squad_club_tid, c.name AS squad_club,
       r.club_tid NOT IN (SELECT o.club_tid FROM ours o
                          WHERE o.season = q.season AND o.phase = q.phase) AS loaned_in,
       r.club_tid AS own_club_tid, r.club AS own_club
       {%- for c in entry_cols %},
       k."{{ c }}"{% endfor %}
FROM squad q
JOIN {{ source('raw', 'players_raw') }} r
  ON r.season = q.season AND r.phase = q.phase AND r.tid = q.tid
LEFT JOIN {{ source('raw', 'clubs') }} c
       ON c.season = q.season AND c.phase = q.phase AND c.tid = q.squad_club_tid
LEFT JOIN latest k ON k.season = q.season AND k.phase = q.phase AND k.player_tid = q.tid
