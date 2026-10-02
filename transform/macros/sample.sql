{#- The sample the ratings tests read, as literals, so DuckDB pushes the filter
    into the views (through the GROUP BY and the windows) instead of computing
    all 16M ratings first: the newest snapshot, 50 of its players by hash, the
    first method and the first role. -#}
{% macro rating_sample() %}
    {%- if not execute -%}
        {{ return({'season': 0, 'phase': '', 'tids': [0],
                   'method': '', 'role': ''}) }}
    {%- endif -%}
    {%- set snapshots = run_query(
        "select season, phase from " ~ source('raw', 'extracts')
        ~ " order by " ~ phase_ord() ~ " desc limit 1").rows -%}
    {%- if not snapshots -%}  {#- an empty store: nothing to sample -#}
        {{ return({'season': 0, 'phase': '', 'tids': [0],
                   'method': '', 'role': ''}) }}
    {%- endif -%}
    {%- set snapshot = snapshots[0] -%}
    {%- set tids = run_query(
        "select tid from " ~ source('raw', 'players_raw')
        ~ " where season = " ~ snapshot[0]
        ~ " and phase = '" ~ snapshot[1] ~ "' and has_attributes"
        ~ " order by hash(tid) limit 50").columns[0].values() -%}
    {%- set first = run_query(
        "select (select min(method) from " ~ source('raw', 'role_weights')
        ~ "), (select min(role) from " ~ source('raw', 'position_role_map')
        ~ ")").rows[0] -%}
    {{ return({'season': snapshot[0], 'phase': snapshot[1],
               'tids': tids | list, 'method': first[0], 'role': first[1]}) }}
{% endmacro %}
