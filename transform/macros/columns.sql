{# The column names of a relation, in order. Empty while dbt parses (nothing is executed then). #}
{% macro column_names(relation) -%}
    {%- if execute -%}
        {{ return(adapter.get_columns_in_relation(relation) | map(attribute='name') | list) }}
    {%- else -%}
        {{ return([]) }}
    {%- endif -%}
{%- endmacro %}

{# chronological order of a phase: dates sort as strings, legacy words as epoch #}
{% macro phase_ord(col='phase') -%}
CASE {{ col }} WHEN 'start' THEN '0000-00-00' WHEN 'mid' THEN '0000-00-01'
     WHEN 'end' THEN '0000-00-02' ELSE {{ col }} END
{%- endmacro %}

{# The game hands a retired person's tid to a newgen, so tid alone splices two careers; (tid,
   dob) separates every recycled slot (docs/IDS.md). person_id is '<tid>-<dob>'. #}
{% macro person_id() -%}
concat(CAST(tid AS VARCHAR), '-', COALESCE(CAST(dob AS VARCHAR), '?'))
{%- endmacro %}

{# A squad player's scrapbook entry is used while it is at most this old #}
{% macro has_entry(k='k') -%}{{ k }}.scrapbook_date IS NOT NULL{%- endmacro %}
{% macro fresh_entry(k='k') -%}
({{ k }}.scrapbook_date IS NOT NULL AND TRY_CAST({{ k }}.phase AS DATE) - {{ k }}.scrapbook_date
 <= {{ var('scrapbook_max_age_days') }})
{%- endmacro %}
