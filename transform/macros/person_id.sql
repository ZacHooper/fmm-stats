{#- The game hands a retired person's tid to a newgen, so tid alone splices two
    careers; (tid, dob) separates every recycled slot (docs/IDS.md).
    person_id is '<tid>-<dob>'. -#}
{% macro person_id(tid='tid', dob='dob') -%}
concat(cast({{ tid }} as varchar), '-', coalesce(cast({{ dob }} as varchar), '?'))
{%- endmacro %}
