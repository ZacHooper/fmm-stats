-- The staff attribute table, one record per staff member who has one, keyed
-- by id2: coaching ability, reputation, the six hidden bytes and the
-- manager's formation triple (formation ids, stg.formations names them).
select
    cast(phase as date) as snapshot_date,
    id2,
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
    formation_defensive
from {{ source('raw', 'staff_records') }}
