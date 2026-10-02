-- Each player's familiarity with every position his attribute record rates
-- above 1, one row per position, by tid.
with long as (
    unpivot {{ ref('int_player_records') }}
    on
    {% for position in var('positions') %}
    pos_{{ position | lower }}{% if not loop.last %},{% endif %}
    {% endfor %}
    into name position_column value familiarity
)

select
    snapshot_date,
    tid,
    upper(replace(position_column, 'pos_', '')) as position,
    familiarity
from long
