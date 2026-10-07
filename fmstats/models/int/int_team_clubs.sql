-- The club each team tid belongs to, keyed team_tid: every team the save
-- holds a record for (its latest snapshot's club, int_teams), and every
-- youth side a career line names. A club's youth side has no record of its
-- own; its tid is the u16 complement of its club's, var('youth_tid_base')
-- minus the club tid (Frem 346 -> "Frem Yth" 65189, FCK 344 -> 65191;
-- mart.youth_clubs, docs/agent-context/homegrown-derivation.md). Club tids
-- and their complements never overlap, so a tid is a team or an academy,
-- never both. A line tid that is neither (a club the save holds no record
-- for) is not here.
with teams as (
    select
        team_tid,
        club_tid
    from {{ ref('int_teams') }}
    qualify
        snapshot_date = max(snapshot_date) over (partition by team_tid)
),

line_teams as (
    select distinct club_tid as team_tid
    from {{ ref('int_player_career_lines') }}
    where club_tid is not null
)

select
    team_tid,
    club_tid,
    false as is_youth_side
from teams
union all
select
    line_teams.team_tid,
    parents.club_tid,
    true as is_youth_side
from line_teams
left join teams as recorded
    on line_teams.team_tid = recorded.team_tid
inner join teams as parents
    on {{ var('youth_tid_base') }} - line_teams.team_tid = parents.team_tid
where recorded.team_tid is null
