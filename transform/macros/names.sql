{#- a name id -> its slot in one of the three id-tables -> the browse string -#}
{% macro name_join(alias, table, col) %}
LEFT JOIN {{ ref('stg_name_ids') }} {{ alias }}i
       ON {{ alias }}i.season = r.season AND {{ alias }}i.phase = r.phase
      AND {{ alias }}i.name_table = '{{ table }}' AND {{ alias }}i.id = r.{{ col }}
LEFT JOIN {{ ref('stg_name_strings') }} {{ alias }}
       ON {{ alias }}.season = r.season AND {{ alias }}.phase = r.phase
      AND {{ alias }}.ordinal = {{ alias }}i.ordinal
{%- endmacro %}
