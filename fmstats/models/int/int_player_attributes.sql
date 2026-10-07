-- Everything a player is rated on, one row per player with an attribute
-- record: the 23 displayed attributes, the nine hidden ones, the eight
-- personality values, his familiarity in every position and his two feet.
-- A displayed attribute is the stated value where the save states it
-- (int.player_attributes_exact), the decoded one otherwise
-- (int.player_attribute_estimates). is_estimated: the player's estimable
-- attributes are decoded, not stated -- they are all stated or none are
-- (a fresh scrapbook entry states them together); the seven plain attributes
-- and Teamwork's closed form are exact either way.
{%- set estimable = estimable_attributes() %}

select
    stated.snapshot_date,
    stated.tid,
    {% for attribute in var('attr_order') %}
    {% if attribute in var('exact_single') %}
    stated."{{ attribute }}",
    {% else %}
    coalesce(
        stated."{{ attribute }}", estimate."{{ attribute }}"
    ) as "{{ attribute }}",
    {% endif %}
    {% endfor %}
    (
        {% for attribute in estimable %}
        stated."{{ attribute }}" is null{% if not loop.last %} or{% endif %}
        {% endfor %}
    ) as is_estimated,
    {% for column in var('hidden_attributes') %}
    record.{{ column }},
    {% endfor %}
    {% for column in var('personality') %}
    person.{{ column }},
    {% endfor %}
    {% for position in var('positions') %}
    record.pos_{{ position | lower }},
    {% endfor %}
    record.foot_left,
    record.foot_right
from {{ ref('int_player_attributes_exact') }} as stated
inner join {{ ref('int_player_attribute_estimates') }} as estimate
    on
        stated.snapshot_date = estimate.snapshot_date
        and stated.tid = estimate.tid
inner join {{ ref('stg_persons') }} as person
    on
        stated.snapshot_date = person.snapshot_date
        and stated.tid = person.tid
inner join {{ ref('stg_player_attributes') }} as record
    on
        person.snapshot_date = record.snapshot_date
        and person.sid = record.sid
