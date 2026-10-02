-- The old raw.players shape (every person, staff included), built from the
-- person and attribute records and int.player_snapshots for fmstats/mart.py
-- until step 17 moves it to the dim/fact tables. Only the old mart reads it.
--   * A player in our squad whose record names another club is loaned_in:
--     club_tid is the team that lists him and parent_club_tid his own club.
--   * A free agent's club_tid is the save's var('no_id16') and his club
--     'Free agent', as the parser stored them.
--   * squad_status is the training row's byte, which the old mart still
--     shows; it is not a squad status (int.player_snapshots leaves it out).
--   * positions is the player's position familiarities as JSON, in the
--     record's order; '{}' for a person with none (staff, or a player with no
--     record).

with records as (
    select
        person.*,
        record.* exclude (snapshot_date, sid),  -- noqa: RF02
        person.sid is null as is_staff,
        coalesce(info.has_attributes, false) as has_attributes,
        info.is_goalkeeper
    from {{ ref('stg_persons') }} as person
    left join {{ ref('stg_player_attributes') }} as record
        on
            person.snapshot_date = record.snapshot_date
            and person.sid = record.sid
    left join {{ ref('int_player_info') }} as info
        on
            person.snapshot_date = info.snapshot_date
            and person.tid = info.tid
),

loans as (
    select
        squad.snapshot_date,
        squad.tid,
        squad.team_tid
    from {{ ref('int_managed_squad') }} as squad
    inner join records as record
        on
            squad.snapshot_date = record.snapshot_date
            and squad.tid = record.tid
    left join {{ ref('stg_club_details') }} as own_club
        on
            record.snapshot_date = own_club.snapshot_date
            and record.club_tid = own_club.tid
    cross join {{ ref('stg_career') }} as career
    where
        coalesce(own_club.main_club_tid, record.club_tid)
        != career.managed_club_tid
),

people as (
    select
        record.*,
        coalesce(loans.team_tid, record.club_tid) as listed_club_tid,
        loans.tid is not null as loaned_in,
        case when loans.tid is not null then record.club_tid end
            as parent_club_tid
    from records as record
    left join loans
        on
            record.snapshot_date = loans.snapshot_date
            and record.tid = loans.tid
)

select
    {{ legacy_key() }},
    people.tid,
    coalesce(players.name, person_names.name) as name,
    people.is_staff,
    coalesce(people.listed_club_tid, {{ var('no_id16') }}) as club_tid,
    coalesce(clubs.name, 'Free agent') as club,
    people.dob,
    people.nationality_id,
    people.has_attributes,
    case
        when not people.is_staff then training.squad_status
    end as squad_status,
    cast(people.is_goalkeeper as integer) as is_gk,
    people.ca,
    people.pa,
    people.reputation,
    cast('{' || concat_ws(
        ', ',
        {% for pos in var('positions') %}
        '"{{ pos }}": '
        || people.pos_{{ pos | lower }}{% if not loop.last %},{% endif %}
        {% endfor %}
    ) || '}' as json) as positions,
    people.foot_left,
    people.foot_right,
    players.value as player_value,
    people.loaned_in,
    people.parent_club_tid,
    parent_clubs.name as parent_club,
    players.wage_units,
    players.wage_gbp,
    players.contract_expiry,
    cast(year(players.contract_expiry) as integer) as contract_expiry_year,
    people.current_reputation,
    people.world_reputation,
    people.international_retired,
    people.squad_number,
    people.preferred_squad_number,
    people.height_cm,
    people.weight_kg,
    {% for column in var('hidden_attributes') %}
    people.{{ column }},
    {% endfor %}
    {% for column in var('attribute_columns').values()
        if column not in var('hidden_attributes') %}
    people.{{ column }},
    {% endfor %}
    {% for column in var('personality') %}
    people.{{ column }},
    {% endfor %}
    people.international_caps,
    people.international_goals,
    people.u21_caps,
    people.u21_goals,
    people.joined_date,
    people.second_nationality_id,
    people.ethnicity,
    players.scrapbook_entry_date as scrapbook_date
from people
{{ join_snapshots('people') }}
left join {{ ref('int_player_info') }} as players
    on
        people.snapshot_date = players.snapshot_date
        and people.tid = players.tid
left join {{ ref('int_person_names') }} as person_names
    on
        people.snapshot_date = person_names.snapshot_date
        and people.tid = person_names.tid
left join {{ ref('stg_clubs') }} as clubs
    on
        people.snapshot_date = clubs.snapshot_date
        and people.listed_club_tid = clubs.tid
left join {{ ref('stg_clubs') }} as parent_clubs
    on
        people.snapshot_date = parent_clubs.snapshot_date
        and people.parent_club_tid = parent_clubs.tid
left join {{ ref('stg_training') }} as training
    on
        people.snapshot_date = training.snapshot_date
        and people.tid = training.tid
