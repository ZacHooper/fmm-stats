{# A model's schema is exactly its folder's (stg / int), not "<target>_<folder>". #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}
