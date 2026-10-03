-- Each member of staff on each snapshot, keyed (person_id, snapshot_date): a
-- person with no player record who has a staff record or is on a team's books
-- (a retired player has neither). team_tid is the team whose books he is on,
-- from his person record, with the rest of the record: nationality,
-- personality, caps and the date he joined. The staff record
-- (has_staff_record) gives coaching ability, reputation, the six unnamed
-- hidden values, the manager's three formations and the two banded values the
-- game displays, Style and the reputation tier.
select
    staff.person_id,
    staff.snapshot_date,
    staff.tid,
    staff.club_tid as team_tid,
    person.nationality_id,
    person.second_nationality_id,
    person.ethnicity,
    {% for column in var('personality') %}
    person.{{ column }},
    {% endfor %}
    person.international_caps,
    person.international_goals,
    person.u21_caps,
    person.u21_goals,
    person.joined_date,
    staff.has_staff_record,
    staff.ca,
    staff.pa,
    staff.home_reputation,
    staff.current_reputation,
    staff.world_reputation,
    staff.attacking_intent,
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
    staff.formation_defensive_name,
    staff.style,
    staff.reputation_tier,
    staff.snapshot_date = max(staff.snapshot_date) over () as is_current
from {{ ref('int_staff_snapshots') }} as staff
inner join {{ ref('stg_persons') }} as person
    on
        staff.snapshot_date = person.snapshot_date
        and staff.tid = person.tid
where staff.has_staff_record or staff.club_tid is not null
