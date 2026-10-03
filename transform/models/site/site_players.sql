-- Every rated player on every snapshot, keyed (snapshot_date, person_id): the
-- row the web app shows for him. His tid and name on the snapshot, the team
-- his record names, his value where the save holds one (value_is_estimated
-- false: our own squad), wage and contract expiry, the 23 attributes, the
-- profile (bio, reputation, personality, the attributes the game does not
-- show) and:
--   origin_club_tid    the club he came out of, and origin_club its name
--                      (dim_person: an academy counts for its club)
--   capital_eligible   that club is on the capital-region signing list
--                      (seeds/eligible_origin_clubs.csv)
--   development        how far he is from his ceiling, as a word: ability
--                      against potential, in var('site_development_bands')
--   positions          each position his record lists, by code: his
--                      familiarity there and his Level %ile, the share of the
--                      players listing it whose ability is below his, among all
--                      of them (level_global) and among those whose team is in
--                      his team's league (level_league); NULL levels where he
--                      has no ability
-- No ability number leaves the view: the percentile is the only form of it.
with listed as (
    {% for position in var('positions') %}
    select
        snapshot_date,
        person_id,
        team_tid,
        ca,
        '{{ position }}' as position,
        pos_{{ position | lower }} as familiarity
    from {{ ref('fact_player_snapshot') }}
    where pos_{{ position | lower }} > 0
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
    players.snapshot_date,
    players.person_id,
    players.tid,
    info.name,
    players.team_tid,
    people.dob,
    case when not players.value_is_estimated then players.value end as value,
    players.wage_gbp,
    players.contract_expiry,
    {% for attribute in var('attr_order') %}
    players."{{ attribute }}",
    {% endfor %}
    players.squad_number,
    players.height_cm,
    players.weight_kg,
    people.origin_club_tid,
    origin.name as origin_club,
    eligible.club_tid is not null as capital_eligible,
    nations.name as nationality,
    players.foot_left,
    players.foot_right,
    players.preferred_squad_number,
    players.joined_date,
    players.international_caps,
    players.international_goals,
    players.u21_caps,
    players.u21_goals,
    players.reputation,
    players.current_reputation,
    players.world_reputation,
    {% for trait in var('site_profile_traits') %}
    players.{{ trait }},
    {% endfor %}
    case
        {% for floor, word in var('site_development_bands') %}
        when
            players.pa is not null
            and players.ca >= {{ floor }} * greatest(players.pa, players.ca)
            then '{{ word }}'
        {% endfor %}
    end as development,
    positions.positions
from {{ ref('fact_player_snapshot') }} as players
inner join {{ ref('dim_person') }} as people
    on players.person_id = people.person_id
left join {{ ref('int_player_info') }} as info
    on
        players.snapshot_date = info.snapshot_date
        and players.tid = info.tid
left join {{ ref('dim_nation') }} as nations
    on players.nationality_id = nations.nation_id
left join {{ ref('dim_club') }} as origin
    on people.origin_club_tid = origin.club_tid
left join {{ ref('stg_eligible_origin_clubs') }} as eligible
    on people.origin_club_tid = eligible.club_tid
left join positions
    on
        players.snapshot_date = positions.snapshot_date
        and players.person_id = positions.person_id
where players.has_attributes
