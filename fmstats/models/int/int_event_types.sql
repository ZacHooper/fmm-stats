-- Every match event type, named or not: the loader's seed (raw.event_types)
-- and any code seen in a match the seed does not name (name NULL). The roles
-- the models give a type come from vars: ends_appearance (a sending-off),
-- is_shootout (a shoot-out kick, never a goal) and scores_for ('for' a goal
-- for the player's side, 'against' an own goal, NULL for the rest).
{%- set scoring = var('scoring_events') %}

with codes as (
    select
        code,
        name
    from {{ ref('stg_event_types') }}
    union
    select distinct
        type_byte as code,
        null as name
    from {{ ref('stg_match_events') }}
    where
        type_byte not in (
            select event_types.code
            from {{ ref('stg_event_types') }} as event_types
        )
)

select
    code,
    name,
    coalesce(
        name in (
            {% for event in var('sending_off_events') %}
            '{{ event }}'{% if not loop.last %},{% endif %}
            {% endfor %}
        ),
        false
    ) as ends_appearance,
    coalesce(
        name in (
            {% for event in var('shootout_events') %}
            '{{ event }}'{% if not loop.last %},{% endif %}
            {% endfor %}
        ),
        false
    ) as is_shootout,
    case name
        {% for event, side in scoring.items() %}
        when '{{ event }}' then '{{ side }}'
        {% endfor %}
    end as scores_for
from codes
