-- Each member of staff on each snapshot, keyed (person_id, snapshot_date): a
-- person with no player record who has a staff record or is on a team's books
-- (a retired player has neither). team_tid is the team whose books he is on,
-- from his person record. The staff record (has_staff_record) gives coaching
-- ability, reputation, the six unnamed hidden values, the manager's three
-- formations and the two banded values the game displays, Style and the
-- reputation tier.
select
    person_id,
    snapshot_date,
    tid,
    club_tid as team_tid,
    has_staff_record,
    ca,
    pa,
    home_reputation,
    current_reputation,
    world_reputation,
    attacking_intent,
    financial_control,
    outfield_coaching,
    goalkeeping_coaching,
    discipline,
    judging_ability,
    judging_potential,
    people_management,
    motivating,
    tactical_knowledge,
    youth_coaching,
    hidden_s18,
    hidden_s20,
    hidden_s24,
    hidden_s26,
    hidden_s27,
    hidden_s28,
    formation_preferred,
    formation_attacking,
    formation_defensive,
    formation_preferred_name,
    formation_attacking_name,
    formation_defensive_name,
    style,
    reputation_tier,
    snapshot_date = max(snapshot_date) over () as is_current
from {{ ref('int_staff_snapshots') }}
where has_staff_record or club_tid is not null
order by person_id, snapshot_date
