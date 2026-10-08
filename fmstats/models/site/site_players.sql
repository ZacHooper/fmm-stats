-- Every rated player on every snapshot, keyed (snapshot_date, person_id): the
-- row the web app shows for him. His tid and name on the snapshot, the team
-- his record names, his value where the save holds one (value_is_estimated
-- false: our own squad), wage and contract expiry, the 23 attributes, the
-- profile (bio, reputation, personality, the attributes the game does not
-- show) and:
--   origin_club_tid    the club he came out of, and origin_club its name
--                      (dim_person: an academy counts for its club)
--   capital_eligible   that club is on the capital-region signing list
--                      (seeds/eligible_origin_clubs.csv); NULL with no origin
--   development        how far he is from his ceiling, as a word: ability
--                      against potential, in var('site_development_bands')
--   positions          each position his record lists, by code: his
--                      familiarity there and his Level %ile, the share of the
--                      players listing it whose ability is below his, among all
--                      of them (level_global) and among those whose team is in
--                      his team's league (level_league); NULL levels where he
--                      has no ability
-- No ability number leaves the view: the percentile is the only form of it.
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
    people.height_cm,
    people.weight_kg,
    people.origin_club_tid,
    origin.name as origin_club,
    people.capital_eligible,
    nations.name as nationality,
    people.foot_left,
    people.foot_right,
    people.preferred_squad_number,
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
    players.positions
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
where players.has_attributes
