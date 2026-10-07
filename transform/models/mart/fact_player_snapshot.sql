-- Reconstructed snapshot-grain view over the SCD Type 2 state table and the
-- valuation table. Preserves backwards compatibility for all downstream models
-- and consumer queries without duplicating data on disk.
{{ config(materialized='view') }}

select
    val.person_id,
    val.snapshot_date,
    scd.tid,
    scd.team_tid,
    scd.club_tid,
    {{ age_on('person.dob', 'val.snapshot_date') }} as age,
    scd.nationality_id,
    scd.second_nationality_id,
    scd.is_goalkeeper,
    scd.has_attributes,
    scd.ca,
    scd.pa,
    val.reputation,
    val.current_reputation,
    val.world_reputation,
    scd.squad_number,
    scd.international_retired,
    scd.international_caps,
    scd.international_goals,
    scd.u21_caps,
    scd.u21_goals,
    scd.joined_date,
    val.value,
    val.value_is_estimated,
    val.value_in_trusted_band,
    scd.scrapbook_entry_date,
    scd.wage_gbp,
    scd.contract_start,
    scd.contract_expiry,
    scd.contract_status,
    scd.is_contracted,
    scd.squad_status,
    scd.training_intensity,
    scd.training_focus_role,
    scd.training_focus_attribute,
    scd.training_focus_position,
    {% for attribute in var('attr_order') %}
    scd."{{ attribute }}",
    {% endfor %}
    scd.attributes_are_estimated,
    {% for column in var('hidden_attributes') %}
    scd.{{ column }},
    {% endfor %}
    {% for column in var('personality') %}
    scd.{{ column }},
    {% endfor %}
    {% for position in var('positions') %}
    scd.pos_{{ position | lower }},
    {% endfor %}
    val.snapshot_date = max(val.snapshot_date) over () as is_current
from {{ ref('fact_player_valuation') }} as val
inner join {{ ref('fact_player_state_scd') }} as scd
    on
        val.person_id = scd.person_id
        and val.snapshot_date >= scd.valid_from
        and val.snapshot_date <= scd.valid_to
inner join {{ ref('stg_persons') }} as person
    on
        val.snapshot_date = person.snapshot_date
        and scd.tid = person.tid
