{#- One row per `key`: the row from its latest snapshot (the max snapshot_date
    it appears in), with that date as last_seen_date. For a dimension's values
    that do not change between snapshots; an id that vanishes from later
    snapshots keeps its last row. -#}
{% macro latest(relation, key) -%}
select
    * exclude (snapshot_date),
    snapshot_date as last_seen_date
from {{ relation }}
qualify snapshot_date = max(snapshot_date) over (partition by {{ key }})
{%- endmacro %}
