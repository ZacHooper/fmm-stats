SELECT e.season, e.phase, e.tid
{%- for a in var('attr_order') %},
       {% if a in var('exact_single') -%}
       e."{{ a }}"
       {%- else -%}
       CASE WHEN {{ fresh_entry() }} THEN k."{{ a }}" ELSE e."{{ a }}" END AS "{{ a }}"
       {%- endif %}
{%- endfor %}
FROM {{ source('raw', 'player_attributes_exact_raw') }} e
LEFT JOIN {{ ref('int_squad_scrapbook') }} k
       ON k.season = e.season AND k.phase = e.phase AND k.tid = e.tid
