-- mart.club_roster on the new layers: every team's squad array on each
-- snapshot (squad_membership), with the team his own record names
-- (owner_club_tid) and whether the listing is a loan in: a club's own side
-- listing another club's player (a national side's call-up is not a loan).
select
    snapshots.season,
    snapshots.phase,
    snapshots.snap_ix,
    snapshots.phase_date,
    squads.team_tid as club_tid,
    squads.tid,
    squads.slot,
    people.name,
    squads.record_team_tid as owner_club_tid,
    squads.is_loan_in
    and squads.team_type in (
        {% for team_type in var('loan_team_types') %}
        '{{ team_type }}'{% if not loop.last %},{% endif %}
        {% endfor %}
    ) as on_loan_in,
    squads.person_id
from {{ ref('squad_membership') }} as squads
inner join {{ ref('site_snapshots') }} as snapshots
    on squads.snapshot_date = snapshots.phase_date
inner join {{ ref('dim_person') }} as people
    on squads.person_id = people.person_id
