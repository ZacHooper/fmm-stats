-- mart.player_career_seasons on the new layers: each player's career history
-- as each snapshot holds it, one row per line (stg_player_history_seasons; the
-- union across snapshots is fact_player_season). seq -1 is the debut line.
select
    snapshots.season,
    snapshots.phase,
    lines.tid,
    people.person_id,
    lines.seq,
    lines.seq < 0 as is_debut,
    lines.hist_season,
    lines.season as end_year,
    lines.club_tid,
    coalesce(teams.name, '#' || lines.club_tid) as club,
    lines.fee_code as fee,
    lines.apps,
    lines.goals,
    lines.assists,
    lines.rating
from {{ ref('stg_player_history_seasons') }} as lines
inner join {{ ref('site_snapshots') }} as snapshots
    on lines.snapshot_date = snapshots.phase_date
left join {{ ref('int_person_snapshots') }} as people
    on
        lines.snapshot_date = people.snapshot_date
        and lines.tid = people.tid
left join {{ ref('int_teams') }} as teams
    on
        lines.snapshot_date = teams.snapshot_date
        and lines.club_tid = teams.team_tid
