-- Fact: one row per (person_id, snapshot_date).
-- Current state + 23 playing attributes + valuation (split from SCD2 to keep wide row count small).
-- Materialized as a view over fact_player_state_scd + fact_player_valuation to serve site models
-- and consumer queries without duplicating data on disk.
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
    scd.parent_club_tid,
    scd.club_tid,
    scd.squad_code,
    scd.age,
    scd.ca,
    scd.pa,
    scd.reputation,
    scd.is_loan,
    scd.is_reserve,
    val.value,
    val.wage,
    val.contract_expires,
    val.min_fee_release,
    scd.corners,
    scd.crossing,
    scd.dribbling,
    scd.finishing,
    scd.first_touch,
    scd.free_kicks,
    scd.heading,
    scd.long_shots,
    scd.long_throws,
    scd.marking,
    scd.passing,
    scd.penalty_taking,
    scd.tackling,
    scd.technique,
    scd.aggression,
    scd.anticipation,
    scd.bravery,
    scd.composure,
    scd.concentration,
    scd.decisions,
    scd.determination,
    scd.flair,
    scd.leadership,
    scd.off_the_ball,
    scd.positioning,
    scd.teamwork,
    scd.vision,
    scd.work_rate,
    scd.acceleration,
    scd.agility,
    scd.balance,
    scd.jumping_reach,
    scd.natural_fitness,
    scd.pace,
    scd.stamina,
    scd.strength,
    scd.aerial_reach,
    scd.command_of_area,
    scd.communication,
    scd.eccentricity,
    scd.handling,
    scd.kicking,
    scd.one_on_ones,
    scd.reflexes,
    scd.rushing_out,
    scd.punching,
    scd.throwing,
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
