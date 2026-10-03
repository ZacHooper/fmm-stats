-- mart.staff on the new layers: every member of staff with a staff record on
-- each snapshot (fact_staff_snapshot), named from dim_person, his team's name
-- from dim_team.
select
    snapshots.season,
    snapshots.phase,
    snapshots.snap_ix,
    snapshots.phase_date,
    staff.tid,
    people.name,
    staff.team_tid as club_tid,
    teams.name as club,
    people.dob,
    staff.nationality_id,
    {% for column in var('personality') %}
    staff.{{ column }},
    {% endfor %}
    staff.international_caps,
    staff.international_goals,
    staff.u21_caps,
    staff.u21_goals,
    staff.joined_date,
    staff.second_nationality_id,
    staff.ethnicity,
    staff.home_reputation,
    staff.current_reputation,
    staff.world_reputation,
    staff.reputation_tier,
    staff.attacking_intent,
    staff.style,
    staff.financial_control,
    staff.outfield_coaching,
    staff.goalkeeping_coaching,
    staff.discipline,
    staff.judging_ability,
    staff.judging_potential,
    staff.people_management,
    staff.motivating,
    staff.tactical_knowledge,
    staff.youth_coaching,
    staff.hidden_s18,
    staff.hidden_s20,
    staff.hidden_s24,
    staff.hidden_s26,
    staff.hidden_s27,
    staff.hidden_s28,
    staff.formation_preferred,
    staff.formation_attacking,
    staff.formation_defensive,
    staff.formation_preferred_name,
    staff.formation_attacking_name,
    staff.formation_defensive_name
from {{ ref('fact_staff_snapshot') }} as staff
inner join {{ ref('site_snapshots') }} as snapshots
    on staff.snapshot_date = snapshots.phase_date
inner join {{ ref('dim_person') }} as people
    on staff.person_id = people.person_id
left join {{ ref('dim_team') }} as teams
    on staff.team_tid = teams.team_tid
where staff.has_staff_record
