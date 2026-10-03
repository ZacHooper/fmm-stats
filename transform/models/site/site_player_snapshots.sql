-- mart.player_snapshots on the new layers: each player on each snapshot
-- (fact_player_snapshot), with his team's league (site.club_leagues), his
-- positions as JSON (position -> familiarity, as the old view carried them),
-- the 16 entangled source bytes of his attribute record (int.player_info's
-- sid into stg_player_attributes), the save's stated value (player_value: the
-- value where it is not the model's) and, for a loanee in our squad, his
-- parent team (squad_membership). est_attrs counts the estimable attributes
-- when they are estimated (all or none are).
{%- set estimable = estimable_attributes() %}

with loans_in as (
    select distinct
        person_id,
        snapshot_date
    from {{ ref('squad_membership') }}
    where is_loan_in and is_managed_club
)

select
    snapshots.season,
    snapshots.phase,
    snapshots.snap_ix,
    snapshots.phase_date,
    player.tid,
    player.person_id,
    people.name,
    player.team_tid as club_tid,
    teams.name as club,
    leagues.league_cid,
    leagues.league_name,
    leagues.nation,
    cast('{' || concat_ws(
        ', ',
        {% for position in var('positions') %}
        '"{{ position }}": '
        || player.pos_{{ position | lower }}{% if not loop.last %},{% endif %}
        {% endfor %}
    ) || '}' as json) as positions,
    people.dob,
    player.age,
    cast(player.is_goalkeeper as integer) as is_gk,
    player.has_attributes,
    player.squad_status,
    player.reputation,
    player.current_reputation,
    player.world_reputation,
    player.international_retired,
    player.squad_number,
    player.preferred_squad_number,
    player.height_cm,
    player.weight_kg,
    {% for column in var('hidden_attributes') %}
    player.{{ column }},
    {% endfor %}
    {% for column in ['crossing_src', 'dribbling_src', 'tackling_src',
                      'finishing_src', 'long_shot_src', 'passing_src',
                      'decision_src', 'creativity_src', 'movement_src',
                      'positioning_src', 'handling_src', 'kicking_src',
                      'aerial_gk_src', 'reflexes_src', 'communication_src',
                      'throwing_src'] %}
    record.{{ column }},
    {% endfor %}
    {% for column in var('personality') %}
    player.{{ column }},
    {% endfor %}
    player.international_caps,
    player.international_goals,
    player.u21_caps,
    player.u21_goals,
    player.joined_date,
    player.second_nationality_id,
    player.ethnicity,
    player.foot_left,
    player.foot_right,
    player.nationality_id,
    case when not player.value_is_estimated then player.value end
        as player_value,
    player.wage_gbp // {{ var('wage_gbp_per_unit') }} as wage_units,
    player.wage_gbp,
    player.contract_expiry,
    cast(year(player.contract_expiry) as integer) as contract_expiry_year,
    loans_in.person_id is not null as loaned_in,
    case when loans_in.person_id is not null then player.team_tid end
        as parent_club_tid,
    case when loans_in.person_id is not null then teams.name end
        as parent_club,
    case
        when player.attributes_are_estimated then {{ estimable | length }}
        when player.has_attributes then 0
    end as est_attrs,
    player.attributes_are_estimated as is_estimated,
    {% for attribute in var('attr_order') %}
    player."{{ attribute }}"{% if not loop.last %},{% endif %}
    {% endfor %}
from {{ ref('fact_player_snapshot') }} as player
inner join {{ ref('site_snapshots') }} as snapshots
    on player.snapshot_date = snapshots.phase_date
inner join {{ ref('dim_person') }} as people
    on player.person_id = people.person_id
left join {{ ref('dim_team') }} as teams
    on player.team_tid = teams.team_tid
left join {{ ref('site_club_leagues') }} as leagues
    on
        snapshots.season = leagues.season
        and snapshots.phase = leagues.phase
        and player.team_tid = leagues.club_tid
left join {{ ref('int_player_info') }} as info
    on
        player.snapshot_date = info.snapshot_date
        and player.tid = info.tid
left join {{ ref('stg_player_attributes') }} as record
    on
        info.snapshot_date = record.snapshot_date
        and info.sid = record.sid
left join loans_in
    on
        player.person_id = loans_in.person_id
        and player.snapshot_date = loans_in.snapshot_date
