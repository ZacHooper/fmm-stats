{#- The sample the ratings tests read, as literals, so DuckDB pushes the filter
    into the views (through the GROUP BY and the windows) instead of computing
    every rating first: the newest snapshot, 50 of its players by hash, the
    first method and the first role. -#}
{% macro rating_sample() %}
    {%- set empty = {'snapshot_date': '1900-01-01', 'tids': [0],
                     'method': '', 'role': ''} -%}
    {%- if not execute -%}{{ return(empty) }}{%- endif -%}
    {%- set snapshots = run_query(
        "select cast(max(snapshot_date) as varchar) from "
        ~ ref('stg_snapshots')).rows -%}
    {%- if snapshots[0][0] is none -%}  {#- an empty store -#}
        {{ return(empty) }}
    {%- endif -%}
    {%- set snapshot_date = snapshots[0][0] -%}
    {%- set tids = run_query(
        "select tid from " ~ ref('int_player_info')
        ~ " where snapshot_date = '" ~ snapshot_date ~ "' and has_attributes"
        ~ " order by hash(tid) limit 50").columns[0].values() -%}
    {%- set first = run_query(
        "select (select min(method) from " ~ ref('stg_role_weights')
        ~ "), (select min(role) from " ~ ref('stg_position_roles')
        ~ ")").rows[0] -%}
    {{ return({'snapshot_date': snapshot_date, 'tids': tids | list,
               'method': first[0], 'role': first[1]}) }}
{% endmacro %}
