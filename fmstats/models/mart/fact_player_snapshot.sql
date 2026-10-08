-- One row per (person_id, snapshot_date): the player's state, attributes and
-- valuation on that snapshot, and in positions each position he can play with
-- its familiarity and Level %ile (level_league, level_global). A view over
-- fact_player_state_scd and fact_player_valuation, so the snapshot grain costs
-- no disk.
{{ config(materialized='view') }}

with listed as (
    {% for position in var('positions') %}
    select
        val.snapshot_date,
        val.person_id,
        scd.team_tid,
        scd.ca,
        '{{ position }}' as position,
        scd.pos_{{ position | lower }} as familiarity
    from {{ ref('fact_player_valuation') }} as val
    inner join {{ ref('fact_player_state_scd') }} as scd
        on
            val.person_id = scd.person_id
            and val.snapshot_date >= scd.valid_from
            and val.snapshot_date <= scd.valid_to
    where scd.pos_{{ position | lower }} > 0
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

levels as (
    select
        listed.snapshot_date,
        listed.person_id,
        listed.position,
        listed.familiarity,
        case
            when listed.ca is not null
                then round(
                    100 * percent_rank() over (
                        partition by
                            listed.snapshot_date,
                            listed.position,
                            listed.ca is null
                        order by listed.ca
                    ),
                    1
                )
        end as level_global,
        case
            when listed.ca is not null
                then round(
                    100 * percent_rank() over (
                        partition by
                            listed.snapshot_date,
                            listed.position,
                            leagues.league_cid,
                            listed.ca is null
                        order by listed.ca
                    ),
                    1
                )
        end as level_league
    from listed
    left join {{ ref('int_team_leagues') }} as leagues
        on
            listed.snapshot_date = leagues.snapshot_date
            and listed.team_tid = leagues.team_tid
),

positions as (
    select
        snapshot_date,
        person_id,
        list(
            {
                'position': position,
                'familiarity': familiarity,
                'level_league': level_league,
                'level_global': level_global
            }
            order by position
        ) as positions
    from levels
    group by snapshot_date, person_id
)

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
    positions.positions,
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
left join positions
    on
        val.snapshot_date = positions.snapshot_date
        and val.person_id = positions.person_id
