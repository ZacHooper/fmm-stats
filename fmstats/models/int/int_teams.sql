-- Every team on each snapshot, one row per club-shaped record, with the club
-- that owns it. The save stores each team as a whole club record; a team that
-- names another in main_club_tid belongs to that club (a reserve side to its
-- first team, a national U21 side to the senior side), and a team that names
-- none is its club's first team and owns itself.
--
-- team_type is the club type named (var('team_types')), except that a
-- first-team-typed record with a parent is a b_team (var('b_team')): a second
-- or third side that plays in the senior pyramid, unlike a reserve side.
{%- set team_types = var('team_types') %}
{%- set b_team = var('b_team') %}

with teams as (
    select
        details.snapshot_date,
        details.tid as team_tid,
        clubs.name,
        details.club_type,
        nullif(details.main_club_tid, details.tid) as parent_tid
    from {{ ref('stg_club_details') }} as details
    left join {{ ref('stg_clubs') }} as clubs
        on
            details.snapshot_date = clubs.snapshot_date
            and details.tid = clubs.tid
)

select
    snapshot_date,
    team_tid,
    coalesce(parent_tid, team_tid) as club_tid,
    name,
    case
        when club_type = {{ b_team.club_type }} and parent_tid is not null
            then '{{ b_team.team_type }}'
        {% for code, team_type in team_types.items() %}
        when club_type = {{ code }} then '{{ team_type }}'
        {% endfor %}
    end as team_type,
    parent_tid is null as is_first_team,
    club_type
from teams
