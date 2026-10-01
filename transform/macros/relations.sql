{#- References leave the database (catalog) out. DuckDB names a store's catalog after its file,
    so a view written as "fm-frem"."int".players stops binding the moment the store is read
    under another name: the cached R2 copy, open_readonly's temp copy, an ATTACH ... AS m. -#}
{% macro ref() -%}
    {{ return(builtins.ref(*varargs, **kwargs).include(database=False)) }}
{%- endmacro %}

{% macro source(source_name, table_name) -%}
    {{ return(builtins.source(source_name, table_name).include(database=False)) }}
{%- endmacro %}
