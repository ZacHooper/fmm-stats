{#- One row per `key`: its latest snapshot's, with that snapshot's date as
    last_seen_date. A dimension's descriptive values are the latest the save
    gives, and an id that vanishes from later snapshots keeps its last row. -#}
{% macro latest(relation, key) -%}
select
    * exclude (snapshot_date),
    snapshot_date as last_seen_date
from {{ relation }}
qualify
    row_number() over (partition by {{ key }} order by snapshot_date desc) = 1
{%- endmacro %}
