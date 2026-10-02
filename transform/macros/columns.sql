{#- The column names of a relation, in order. Empty while dbt parses (nothing
    is executed then). -#}
{% macro column_names(relation) -%}
    {%- if execute -%}
        {{ return(adapter.get_columns_in_relation(relation)
                  | map(attribute='name') | list) }}
    {%- else -%}
        {{ return([]) }}
    {%- endif -%}
{%- endmacro %}

{#- Chronological order of a phase: dates sort as strings, the legacy words
    as epoch. -#}
{% macro phase_ord(col='phase') -%}
case {{ col }}
    when 'start' then '0000-00-00'
    when 'mid' then '0000-00-01'
    when 'end' then '0000-00-02'
    else {{ col }}
end
{%- endmacro %}

{#- The game hands a retired person's tid to a newgen, so tid alone splices two
    careers; (tid, dob) separates every recycled slot (docs/IDS.md).
    person_id is '<tid>-<dob>'. -#}
{% macro person_id() -%}
concat(cast(tid as varchar), '-', coalesce(cast(dob as varchar), '?'))
{%- endmacro %}

{#- A squad player's scrapbook entry stands in for his record while it is at
    most var('scrapbook_max_age_days') old. -#}
{% macro fresh_entry(entry='entry') -%}
(
    {{ entry }}.scrapbook_date is not null
    and try_cast({{ entry }}.phase as date) - {{ entry }}.scrapbook_date
    <= {{ var('scrapbook_max_age_days') }}
)
{%- endmacro %}
