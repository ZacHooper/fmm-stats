{# A model file is named <layer>_<name> (dbt needs unique names); its relation is <layer>.<name>,
   e.g. models/int/int_player_info.sql -> int.player_info. #}
{% macro generate_alias_name(custom_alias_name=none, node=none) -%}
    {%- if custom_alias_name -%}
        {{ custom_alias_name | trim }}
    {%- elif node.config.schema and node.name.startswith(node.config.schema ~ '_') -%}
        {{ node.name[node.config.schema | length + 1:] }}
    {%- else -%}
        {{ node.name }}
    {%- endif -%}
{%- endmacro %}
