{#- The grain test: the key columns are unique together and never NULL. dbt's
    built-in unique / not_null take one column; every grain here is composite. -#}
{% test unique_combination(model, columns) %}
select
    {{ columns | join(',\n    ') }},
    count(*) as n
from {{ model }}
group by all
having count(*) > 1 or {{ columns | join(' is null or ') }} is null
{% endtest %}

{#- Every non-NULL key in `columns` exists in `to` as `to_columns`. -#}
{% test relationship_combination(model, columns, to, to_columns) %}
select child.*
from {{ model }} as child
where
    {% for c in columns -%}
    child.{{ c }} is not null and
    {% endfor -%}
    not exists (
        select 1
        from {{ to }} as parent
        where
            {% for c in columns -%}
            parent.{{ to_columns[loop.index0] }} = child.{{ c }}
            {%- if not loop.last %} and{% endif %}
            {% endfor %}
    )
{% endtest %}
