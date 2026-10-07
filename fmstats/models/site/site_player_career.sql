-- Each player's career history as the game reports it, one row per line,
-- keyed (person_id, line_index): the season (its end year), the team and its
-- name (a youth side, which the save does not name, reads as its club), the
-- fee code on the line and the season's appearances, goals, assists and
-- average rating. fee_label is the code as the profile shows it: the fee in
-- pounds, or loan / free / stay / contract ended; NULL for a code not
-- understood.
select
    career_lines.person_id,
    career_lines.line_index,
    career_lines.season,
    career_lines.team_tid,
    coalesce(teams.name, youth_clubs.name, '#' || career_lines.team_tid)
        as club,
    career_lines.fee_kind,
    career_lines.fee_gbp,
    case career_lines.fee_kind
        when 'fee' then '£' || format('{:,}', career_lines.fee_gbp)
        when 'contract_ended' then 'contract ended'
        when 'unknown' then null
        else career_lines.fee_kind
    end as fee_label,
    career_lines.apps,
    career_lines.goals,
    career_lines.assists,
    career_lines.rating
from {{ ref('fact_player_season') }} as career_lines
left join {{ ref('dim_team') }} as teams
    on career_lines.team_tid = teams.team_tid
left join {{ ref('int_team_clubs') }} as team_clubs
    on career_lines.team_tid = team_clubs.team_tid and team_clubs.is_youth_side
left join {{ ref('dim_club') }} as youth_clubs
    on team_clubs.club_tid = youth_clubs.club_tid
