{#- The attribute decode: one SQL expression per derived attribute, generated from its
    coefficient rows in raw.attribute_model. `own`/`partner` are the wrapped 0-255 source
    columns (named in stg.attribute_model); everything else is read straight off the stored record. -#}

{% macro uw(c) -%}(CASE WHEN {{ c }} < 128 THEN {{ c }} + 256 ELSE {{ c }} END){%- endmacro %}

{#- A coefficient as an explicit DOUBLE. Written bare, DuckDB reads a 16-digit literal as
    DECIMAL(18) and the first multiplication by a byte value overflows. -#}
{% macro dbl(c) -%}CAST({{ c }} AS DOUBLE){%- endmacro %}

{% macro mean9() -%}
((p.heading_src + p.unselfishness_src + p.pace_src + p.strength_src + p.stamina_src + p.technique_src + p.aggression_src + p.leadership_src + p.agility_src) / 9.0)
{%- endmacro %}

{#- fwd: attacking-ness of the player's best position; a tie goes to the position the record
    lists first (var positions), so a player equally good at DC and ST resolves to DC. -#}
{% macro fwd() -%}
(SELECT CASE WHEN t.position IN ('ST','AML','AMR','AMC') THEN 1.0
             WHEN t.position IN ('ML','MR','MC','DMC','DML','DMR') THEN 0.5
             ELSE 0.0 END
   FROM {{ source('raw', 'player_positions') }} t
  WHERE (t.season, t.phase, t.tid) = (p.season, p.phase, p.tid)
  ORDER BY t.familiarity DESC, (CASE t.position
      {%- for pos in var('positions') %} WHEN '{{ pos }}' THEN {{ loop.index0 }}{% endfor %} END)
  LIMIT 1)
{%- endmacro %}

{% macro familiarity(pos) -%}
COALESCE((SELECT t.familiarity FROM {{ source('raw', 'player_positions') }} t WHERE (t.season,t.phase,t.tid)=(p.season,p.phase,p.tid) AND t.position = '{{ pos }}'), 0)
{%- endmacro %}

{#- floor(w1*b1 + w2*b2 + off), clipped 1-20 -#}
{% macro composite(b1, b2, w) -%}
GREATEST(1, LEAST(20, CAST(floor({{ dbl(w[0]) }} * p.{{ b1 }} + {{ dbl(w[1]) }} * p.{{ b2 }} + {{ dbl(w[2]) }}) AS INTEGER)))
{%- endmacro %}

{#- One attribute's fitted value from its coefficient rows. -#}
{% macro model_expr(spec) -%}
{%- set own = uw('p."' ~ spec.own ~ '"') -%}
{%- set parts = [] -%}
{%- for feat, c in spec.coef.items() -%}
    {%- if feat == 'intercept' -%}{%- do parts.append(dbl(c)) -%}
    {%- else -%}
        {%- if feat == 'own' -%}{%- set e = own -%}
        {%- elif feat == 'partner' -%}{%- set e = uw('p."' ~ spec.partner ~ '"') -%}
        {%- elif feat == 'CA' -%}{%- set e = 'p.ca' -%}
        {%- elif feat == 'PA' -%}{%- set e = 'p.pa' -%}
        {%- elif feat == 'mean9' -%}{%- set e = mean9() -%}
        {%- elif feat == 'own*CA' -%}{%- set e = '(' ~ own ~ ' * p.ca / 100.0)' -%}
        {%- elif feat == 'fwd' -%}{%- set e = fwd() -%}
        {%- elif feat in var('hidden_attributes') -%}{%- set e = 'p."' ~ feat ~ '"' -%}
        {%- elif feat.startswith('NAT_') and feat[4:] in var('positions') -%}
            {%- set e = 'CASE WHEN ' ~ familiarity(feat[4:]) ~ ' >= 20 THEN 1.0 ELSE 0.0 END' -%}
        {%- elif feat in var('positions') -%}{%- set e = familiarity(feat) -%}
        {%- else -%}{{ exceptions.raise_compiler_error("unknown model feature " ~ feat) }}
        {%- endif -%}
        {%- do parts.append('(' ~ dbl(c) ~ ' * ' ~ e ~ ')') -%}
    {%- endif -%}
{%- endfor -%}
GREATEST(1, LEAST(20, CAST(round({{ parts | join(' + ') }}) AS INTEGER)))
{%- endmacro %}
