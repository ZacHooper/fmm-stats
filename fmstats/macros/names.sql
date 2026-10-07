{#- A name id -> its slot in one of the three id-tables -> the browse string.
    `table` is first_names, surnames or nicknames, and names the joined string. -#}
{% macro name_join(table, id_column) %}
left join {{ ref('stg_name_ids') }} as {{ table }}_slot
    on
        record.snapshot_date = {{ table }}_slot.snapshot_date
        and {{ table }}_slot.name_table = '{{ table }}'
        and record.{{ id_column }} = {{ table }}_slot.id
left join {{ ref('stg_name_strings') }} as {{ table }}
    on
        {{ table }}_slot.snapshot_date = {{ table }}.snapshot_date
        and {{ table }}_slot.ordinal = {{ table }}.ordinal
{%- endmacro %}
