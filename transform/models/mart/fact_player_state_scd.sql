-- Core player state captured as a Slowly Changing Dimension (SCD Type 2),
-- keyed (person_id, valid_from). Each row represents an interval during which
-- a player's team, contract, and ratings remained unchanged.
with player_state as (
    select
        info.person_id,
        info.snapshot_date,
        info.tid,
        info.club_tid as team_tid,
        teams.club_tid,
        info.nationality_id,
        info.second_nationality_id,
        info.is_goalkeeper,
        info.has_attributes,
        info.ca,
        info.pa,
        info.squad_number,
        info.international_retired,
        info.international_caps,
        info.international_goals,
        info.u21_caps,
        info.u21_goals,
        info.joined_date,
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
        -- Hash of all non-temporal state columns to detect true state changes
        md5(concat_ws('||',
            coalesce(cast(info.tid as varchar), ''),
            coalesce(cast(info.club_tid as varchar), ''),
            coalesce(cast(teams.club_tid as varchar), ''),
            coalesce(cast(info.nationality_id as varchar), ''),
            coalesce(cast(info.second_nationality_id as varchar), ''),
            coalesce(cast(info.is_goalkeeper as varchar), ''),
            coalesce(cast(info.has_attributes as varchar), ''),
            coalesce(cast(info.ca as varchar), ''),
            coalesce(cast(info.pa as varchar), ''),
            coalesce(cast(info.squad_number as varchar), ''),
            coalesce(cast(info.international_retired as varchar), ''),
            coalesce(cast(info.international_caps as varchar), ''),
            coalesce(cast(info.international_goals as varchar), ''),
            coalesce(cast(info.u21_caps as varchar), ''),
            coalesce(cast(info.u21_goals as varchar), ''),
            coalesce(cast(info.joined_date as varchar), ''),
            coalesce(cast(info.wage_gbp as varchar), ''),
            coalesce(cast(info.contract_start as varchar), ''),
            coalesce(cast(info.contract_expiry as varchar), ''),
            coalesce(cast(training.is_contracted as varchar), ''),
            coalesce(cast(training.squad_status as varchar), ''),
            coalesce(cast(info.training_intensity as varchar), ''),
            coalesce(cast(info.training_focus_role as varchar), ''),
            coalesce(cast(info.training_focus_attribute as varchar), ''),
            coalesce(cast(info.training_focus_position as varchar), ''),
            {% for attribute in var('attr_order') %}
            coalesce(cast(ratings."{{ attribute }}" as varchar), ''),
            {% endfor %}
            coalesce(cast(ratings.is_estimated as varchar), ''),
            {% for column in var('hidden_attributes') %}
            coalesce(cast(ratings.{{ column }} as varchar), ''),
            {% endfor %}
            {% for column in var('personality') %}
            coalesce(cast(ratings.{{ column }} as varchar), ''),
            {% endfor %}
            {% for position in var('positions') %}
            coalesce(cast(ratings.pos_{{ position | lower }} as varchar), ''){% if not loop.last %},{% endif %}
            {% endfor %}
        )) as state_hash
    from {{ ref('int_player_info') }} as info
    left join {{ ref('int_teams') }} as teams
        on
            info.snapshot_date = teams.snapshot_date
            and info.club_tid = teams.team_tid
    left join {{ ref('int_player_attributes') }} as ratings
        on
            info.snapshot_date = ratings.snapshot_date
            and info.tid = ratings.tid
    left join {{ ref('stg_training') }} as training
        on
            info.snapshot_date = training.snapshot_date
            and info.tid = training.tid
),

lagged as (
    select
        *,
        lag(state_hash) over (
            partition by person_id order by snapshot_date
        ) as prev_state_hash
    from player_state
),

runs as (
    select
        *,
        sum(case when prev_state_hash is null or state_hash != prev_state_hash then 1 else 0 end)
            over (partition by person_id order by snapshot_date) as run_id
    from lagged
),

intervals as (
    select
        person_id,
        run_id,
        min(snapshot_date) as valid_from,
        max(snapshot_date) as valid_to,
        max(snapshot_date) = max(max(snapshot_date)) over () as is_current,
        first(tid) as tid,
        first(team_tid) as team_tid,
        first(club_tid) as club_tid,
        first(nationality_id) as nationality_id,
        first(second_nationality_id) as second_nationality_id,
        first(is_goalkeeper) as is_goalkeeper,
        first(has_attributes) as has_attributes,
        first(ca) as ca,
        first(pa) as pa,
        first(squad_number) as squad_number,
        first(international_retired) as international_retired,
        first(international_caps) as international_caps,
        first(international_goals) as international_goals,
        first(u21_caps) as u21_caps,
        first(u21_goals) as u21_goals,
        first(joined_date) as joined_date,
        first(scrapbook_entry_date) as scrapbook_entry_date,
        first(wage_gbp) as wage_gbp,
        first(contract_start) as contract_start,
        first(contract_expiry) as contract_expiry,
        first(contract_status) as contract_status,
        first(is_contracted) as is_contracted,
        first(squad_status) as squad_status,
        first(training_intensity) as training_intensity,
        first(training_focus_role) as training_focus_role,
        first(training_focus_attribute) as training_focus_attribute,
        first(training_focus_position) as training_focus_position,
        {% for attribute in var('attr_order') %}
        first("{{ attribute }}") as "{{ attribute }}",
        {% endfor %}
        first(attributes_are_estimated) as attributes_are_estimated,
        {% for column in var('hidden_attributes') %}
        first({{ column }}) as {{ column }},
        {% endfor %}
        {% for column in var('personality') %}
        first({{ column }}) as {{ column }},
        {% endfor %}
        {% for position in var('positions') %}
        first(pos_{{ position | lower }}) as pos_{{ position | lower }}{% if not loop.last %},{% endif %}
        {% endfor %}
    from runs
    group by person_id, run_id
)

select
    person_id,
    valid_from,
    valid_to,
    is_current,
    tid,
    team_tid,
    club_tid,
    nationality_id,
    second_nationality_id,
    is_goalkeeper,
    has_attributes,
    ca,
    pa,
    squad_number,
    international_retired,
    international_caps,
    international_goals,
    u21_caps,
    u21_goals,
    joined_date,
    scrapbook_entry_date,
    wage_gbp,
    contract_start,
    contract_expiry,
    contract_status,
    is_contracted,
    squad_status,
    training_intensity,
    training_focus_role,
    training_focus_attribute,
    training_focus_position,
    {% for attribute in var('attr_order') %}
    "{{ attribute }}",
    {% endfor %}
    attributes_are_estimated,
    {% for column in var('hidden_attributes') %}
    {{ column }},
    {% endfor %}
    {% for column in var('personality') %}
    {{ column }},
    {% endfor %}
    {% for position in var('positions') %}
    pos_{{ position | lower }}{% if not loop.last %},{% endif %}
    {% endfor %}
from intervals
