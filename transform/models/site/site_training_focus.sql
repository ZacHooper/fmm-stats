-- mart.training_focus on the new layers: each player's training focus on each
-- snapshot (fact_player_snapshot's training row), with the role and
-- attribute names.
select
    players.season,
    players.phase,
    players.snap_ix,
    players.tid,
    players.person_id,
    players.name,
    players.club_tid,
    players.club,
    facts.training_focus_position as focus_position,
    facts.training_focus_role as focus_role,
    roles.name as focus_role_name,
    roles.inferred as focus_role_inferred,
    facts.training_focus_attribute as focus_attribute,
    attributes.abbrev as focus_attribute_abbrev,
    facts.training_intensity as intensity,
    case facts.training_intensity
        when 3 then 'High' when 2 then 'Normal'
    end as intensity_label
from {{ ref('site_player_snapshots') }} as players
inner join {{ ref('fact_player_snapshot') }} as facts
    on
        players.person_id = facts.person_id
        and players.phase_date = facts.snapshot_date
left join {{ ref('site_roles') }} as roles
    on facts.training_focus_role = roles.id
left join {{ ref('site_training_attributes') }} as attributes
    on facts.training_focus_attribute = attributes.code
