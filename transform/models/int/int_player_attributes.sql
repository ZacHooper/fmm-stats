{#- All 23 attributes with an `_est` flag each: stated where the save states them, decoded from
    the record's attribute columns and stg.attribute_model otherwise. The two composites are closed forms
    over two plain 1-20 attribute columns, no model; Teamwork's is exact (`_est` FALSE), Aerial's matches
    about 71% of the time, so it is an estimate. -#}
{#- spec: {attribute: {own, partner, coef: {feature: coefficient}}}, from stg.attribute_model, in
    its seeded order (the decode sums in it). own / partner name the players_raw columns. -#}
{%- set spec = {} -%}
{%- if execute -%}
    {%- set rows = run_query("SELECT attribute, feature, coef, own_column, partner_column FROM "
                             ~ ref('stg_attribute_model') ~ " ORDER BY seq") -%}
    {%- for r in rows -%}
        {%- if r[0] not in spec -%}{%- do spec.update({r[0]: {'own': r[3], 'partner': r[4], 'coef': {}}}) -%}{%- endif -%}
        {%- do spec[r[0]].coef.update({r[1]: r[2]}) -%}
    {%- endfor -%}
{%- endif -%}
{%- set comps = var('composites') -%}
SELECT p.season, p.phase, p.tid
{%- for a in var('attr_order') %},
       {% if a in comps -%}
       {#- a composite: clip(floor(w1 * column1 + w2 * column2 + offset), 1, 20) over its two
           named columns, where the save does not state the value -#}
       COALESCE(e."{{ a }}", {{ composite(comps[a].columns[0], comps[a].columns[1], comps[a].w) }}) AS "{{ a }}",
       {{ '(e."' ~ a ~ '" IS NULL)' if comps[a].estimate else 'FALSE' }} AS "{{ a }}_est"
       {%- elif a in spec -%}
       COALESCE(e."{{ a }}", {{ model_expr(spec[a]) }}) AS "{{ a }}",
       (e."{{ a }}" IS NULL) AS "{{ a }}_est"
       {%- else -%}
       e."{{ a }}" AS "{{ a }}",
       FALSE AS "{{ a }}_est"
       {%- endif %}
{%- endfor %}
FROM {{ ref('int_players') }} p
JOIN {{ ref('int_player_attributes_exact') }} e USING (season, phase, tid)
-- depends_on: {{ ref('stg_attribute_model') }}  (read by run_query above)
