{#- The attribute decode: one SQL expression per derived attribute, generated
    from its coefficient rows in raw.attribute_model. `own` and `partner` are
    the wrapped 0-255 source columns (named in stg.attribute_model); everything else is read straight off the
    stored record (alias `record`). -#}

{#- {attribute: {own, partner, coef: {feature: coefficient}}}, from
    stg.attribute_model in its seeded order (the sum's order, which floating
    point makes part of the result). own / partner name the players_raw columns
    the attribute reads. -#}
{% macro attribute_model() %}
    {%- set spec = {} -%}
    {%- if execute -%}
        {%- set rows = run_query(
            "select attribute, feature, coef, own_column, partner_column from "
            ~ ref('stg_attribute_model') ~ " order by seq") -%}
        {%- for r in rows -%}
            {%- if r[0] not in spec -%}
                {%- do spec.update({r[0]: {'own': r[3], 'partner': r[4],
                                           'coef': {}}}) -%}
            {%- endif -%}
            {%- do spec[r[0]].coef.update({r[1]: r[2]}) -%}
        {%- endfor -%}
    {%- endif -%}
    {{ return(spec) }}
{% endmacro %}

{% macro uw(c) -%}
(case when {{ c }} < 128 then {{ c }} + 256 else {{ c }} end)
{%- endmacro %}

{#- A coefficient as an explicit DOUBLE. Written bare, DuckDB reads a 16-digit
    literal as DECIMAL(18) and the first multiplication by a byte overflows. -#}
{% macro dbl(c) -%}cast({{ c }} as double){%- endmacro %}

{% macro mean9() -%}
((record.heading_src + record.unselfishness_src + record.pace_src
  + record.strength_src + record.stamina_src + record.technique_src
  + record.aggression_src + record.leadership_src + record.agility_src) / 9.0)
{%- endmacro %}

{#- fwd: attacking-ness of the player's best position; a tie goes to the
    position the record lists first (var positions), so a player equally good
    at DC and ST resolves to DC. -#}
{% macro fwd() -%}
(
    select
        case
            when positions.position in ('ST', 'AML', 'AMR', 'AMC') then 1.0
            when positions.position in ('ML', 'MR', 'MC', 'DMC', 'DML', 'DMR')
                then 0.5
            else 0.0
        end
    from {{ source('raw', 'player_positions') }} as positions
    where
        positions.season = record.season
        and positions.phase = record.phase
        and positions.tid = record.tid
    order by
        positions.familiarity desc,
        case positions.position
            {%- for pos in var('positions') %}
            when '{{ pos }}' then {{ loop.index0 }}
            {%- endfor %}
        end
    limit 1
)
{%- endmacro %}

{% macro familiarity(pos) -%}
coalesce((
    select positions.familiarity
    from {{ source('raw', 'player_positions') }} as positions
    where
        positions.season = record.season
        and positions.phase = record.phase
        and positions.tid = record.tid
        and positions.position = '{{ pos }}'
), 0)
{%- endmacro %}

{#- floor(w1*b1 + w2*b2 + offset), clipped 1-20 -#}
{% macro composite(b1, b2, w) -%}
greatest(1, least(20, cast(floor(
    {{ dbl(w[0]) }} * record.{{ b1 }}
    + {{ dbl(w[1]) }} * record.{{ b2 }}
    + {{ dbl(w[2]) }}
) as integer)))
{%- endmacro %}

{#- One attribute's fitted value from its coefficient rows. -#}
{% macro model_expr(spec) -%}
{%- set own = uw('record."' ~ spec.own ~ '"') -%}
{%- set parts = [] -%}
{%- for feat, c in spec.coef.items() -%}
    {%- if feat == 'intercept' -%}{%- do parts.append(dbl(c)) -%}
    {%- else -%}
        {%- if feat == 'own' -%}{%- set e = own -%}
        {%- elif feat == 'partner' -%}
            {%- set e = uw('record."' ~ spec.partner ~ '"') -%}
        {%- elif feat == 'CA' -%}{%- set e = 'record.ca' -%}
        {%- elif feat == 'PA' -%}{%- set e = 'record.pa' -%}
        {%- elif feat == 'mean9' -%}{%- set e = mean9() -%}
        {%- elif feat == 'own*CA' -%}
            {%- set e = '(' ~ own ~ ' * record.ca / 100.0)' -%}
        {%- elif feat == 'fwd' -%}{%- set e = fwd() -%}
        {%- elif feat in var('hidden_attributes') -%}
            {%- set e = 'record."' ~ feat ~ '"' -%}
        {%- elif feat.startswith('NAT_') and feat[4:] in var('positions') -%}
            {%- set e = '(case when ' ~ familiarity(feat[4:])
                        ~ ' >= 20 then 1.0 else 0.0 end)' -%}
        {%- elif feat in var('positions') -%}{%- set e = familiarity(feat) -%}
        {%- else -%}
            {{ exceptions.raise_compiler_error("unknown model feature " ~ feat) }}
        {%- endif -%}
        {%- do parts.append('(' ~ dbl(c) ~ ' * ' ~ e ~ ')') -%}
    {%- endif -%}
{%- endfor -%}
greatest(1, least(20, cast(round(
    {{ parts | join('\n    + ') }}
) as integer)))
{%- endmacro %}
