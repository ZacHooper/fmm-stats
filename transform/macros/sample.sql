{#- The sample the ratings tests read, as literals so DuckDB pushes the filter into the views
    (through the GROUP BY and the windows) instead of computing all 16M ratings first:
    the newest snapshot, 50 of its players by hash, the first method and the first role. -#}
{% macro rating_sample() %}
    {%- if not execute -%}{{ return({'season': 0, 'phase': '', 'tids': [0], 'method': '', 'role': ''}) }}{%- endif -%}
    {%- set snap = run_query("SELECT season, phase FROM " ~ source('raw', 'extracts')
                             ~ " ORDER BY " ~ phase_ord() ~ " DESC LIMIT 1").rows[0] -%}
    {%- set tids = run_query("SELECT tid FROM " ~ source('raw', 'players_raw')
                             ~ " WHERE season = " ~ snap[0] ~ " AND phase = '" ~ snap[1]
                             ~ "' AND has_attributes ORDER BY hash(tid) LIMIT 50").columns[0].values() -%}
    {%- set mr = run_query("SELECT (SELECT min(method) FROM " ~ source('raw', 'role_weights')
                           ~ "), (SELECT min(role) FROM " ~ source('raw', 'position_role_map') ~ ")").rows[0] -%}
    {{ return({'season': snap[0], 'phase': snap[1], 'tids': tids | list,
               'method': mr[0], 'role': mr[1]}) }}
{% endmacro %}
