-- Every Scrapbook Profile the save holds: one row per entry in each list, a
-- copy of the player's profile screen as it was on entry_date. Lists
-- var('club_lists') are our club's (the Manager's Best Eleven); the rest are
-- the world's. role is the profile's role id (mart.roles names it).
select
    cast(phase as date) as snapshot_date,
    list,
    list_season,
    slot,
    player_tid,
    scrapbook_date as entry_date,
    full_name,
    first_name,
    last_name,
    competition,
    club_tid,
    loan_club_tid,
    age,
    role,
    {% for attribute in var('attr_order') %}
    "{{ attribute }}",
    {% endfor %}
    condition,
    morale,
    form_1,
    form_2,
    form_3,
    form_4,
    form_5,
    avg_rating,
    {% for position in var('positions') %}
    pos_{{ position | lower }},
    {% endfor %}
    value,
    wage,
    caps,
    intl_goals,
    u21_caps,
    u21_goals,
    apps,
    goals,
    conceded,
    assists,
    yellows,
    foot_left,
    foot_right,
    colour_1,
    colour_2
from {{ source('raw', 'player_scrapbook') }}
