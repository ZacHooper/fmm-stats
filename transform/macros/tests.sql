{# The grain test: the key columns are unique together and never NULL. dbt's built-in unique /
   not_null take one column; every grain here is composite. #}
{% test unique_combination(model, columns) %}
SELECT {{ columns | join(', ') }}, count(*) AS n
FROM {{ model }}
GROUP BY ALL
HAVING count(*) > 1 OR {{ columns | join(' IS NULL OR ') }} IS NULL
{% endtest %}

{# Every non-NULL key in `columns` exists in `to` as `to_columns`. #}
{% test relationship_combination(model, columns, to, to_columns) %}
SELECT x.*
FROM {{ model }} x
WHERE {% for c in columns %}x.{{ c }} IS NOT NULL{{ ' AND ' if not loop.last }}{% endfor %}
  AND NOT EXISTS (
      SELECT 1 FROM {{ to }} t
      WHERE {% for c in columns %}t.{{ to_columns[loop.index0] }} = x.{{ c }}{{ ' AND ' if not loop.last }}{% endfor %})
{% endtest %}
