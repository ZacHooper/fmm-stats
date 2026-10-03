-- Each player on each snapshot, keyed (person_id, snapshot_date): everything
-- about him that can change. team_tid is the team whose books he is on (his
-- own record; a loanee's is his parent team) and club_tid the club that owns
-- it; which team lists him is the squads'. Ratings: the 23 displayed
-- attributes (attributes_are_estimated: decoded rather than stated, see
-- int.player_attributes), the nine hidden ones, the eight personality values,
-- his familiarity in every position and his feet; all NULL for a player the
-- save holds no attribute record for (has_attributes). value is the save's
-- where it states one (our squad's fresh scrapbook entries), else the
-- transfer-value model's (value_is_estimated; value_in_trusted_band: the
-- estimate lies in the range the model was validated in). contract_status:
-- 'free_agent' with no team, else 'contracted' or 'expired' by his current
-- contract's expiry against the snapshot date, NULL with no contract on
-- record; is_contracted is the save's own flag on his training row, which does
-- not always agree.

select
    info.person_id,
    info.snapshot_date,
    info.tid,
    info.club_tid as team_tid,
    teams.club_tid,
    {{ age_on('person.dob', 'info.snapshot_date') }} as age,
    info.nationality_id,
    info.second_nationality_id,
    info.ethnicity,
    info.is_goalkeeper,
    info.has_attributes,
    info.ca,
    info.pa,
    info.reputation,
    info.current_reputation,
    info.world_reputation,
    info.height_cm,
    info.weight_kg,
    info.squad_number,
    info.preferred_squad_number,
    info.international_retired,
    info.international_caps,
    info.international_goals,
    info.u21_caps,
    info.u21_goals,
    info.joined_date,
    coalesce(info.value, valuation.value_estimate) as value,
    info.value is null and valuation.value_estimate is not null
        as value_is_estimated,
    case when info.value is null then valuation.is_in_trusted_band end
        as value_in_trusted_band,
    info.scrapbook_entry_date,
    info.wage_gbp,
    info.contract_start,
    info.contract_expiry,
    case
        when info.club_tid is null then 'free_agent'
        when info.contract_expiry >= info.snapshot_date then 'contracted'
        when info.contract_expiry < info.snapshot_date then 'expired'
    end as contract_status,
    training.is_contracted,
    training.squad_status,
    info.training_intensity,
    info.training_focus_role,
    info.training_focus_attribute,
    info.training_focus_position,
    {% for attribute in var('attr_order') %}
    ratings."{{ attribute }}",
    {% endfor %}
    ratings.is_estimated as attributes_are_estimated,
    {% for column in var('hidden_attributes') %}
    ratings.{{ column }},
    {% endfor %}
    {% for column in var('personality') %}
    ratings.{{ column }},
    {% endfor %}
    {% for position in var('positions') %}
    ratings.pos_{{ position | lower }},
    {% endfor %}
    ratings.foot_left,
    ratings.foot_right,
    info.snapshot_date = max(info.snapshot_date) over () as is_current
from {{ ref('int_player_info') }} as info
inner join {{ ref('stg_persons') }} as person
    on
        info.snapshot_date = person.snapshot_date
        and info.tid = person.tid
left join {{ ref('int_teams') }} as teams
    on
        info.snapshot_date = teams.snapshot_date
        and info.club_tid = teams.team_tid
left join {{ ref('int_player_attributes') }} as ratings
    on
        info.snapshot_date = ratings.snapshot_date
        and info.tid = ratings.tid
left join {{ ref('int_player_value') }} as valuation
    on
        info.snapshot_date = valuation.snapshot_date
        and info.tid = valuation.tid
left join {{ ref('stg_training') }} as training
    on
        info.snapshot_date = training.snapshot_date
        and info.tid = training.tid
