-- Every team's squad on each snapshot, one row per player listed, with the
-- club that owns the team: a reserve side names its first team in
-- main_club_tid; a first team or a national side owns itself. A player can be
-- listed by more than one team (a loanee is listed by both clubs for a while),
-- so this is the listing, not a verdict on where he plays.
{%- set team_types = var('team_types') %}

select
    squads.snapshot_date,
    squads.team_tid,
    squads.player_tid,
    squads.slot,
    case details.club_type
        {% for code, team_type in team_types.items() %}
        when {{ code }} then '{{ team_type }}'
        {% endfor %}
    end as team_type,
    coalesce(details.main_club_tid, squads.team_tid) as club_tid
from {{ ref('stg_team_squads') }} as squads
left join {{ ref('stg_club_details') }} as details
    on
        squads.snapshot_date = details.snapshot_date
        and squads.team_tid = details.tid
