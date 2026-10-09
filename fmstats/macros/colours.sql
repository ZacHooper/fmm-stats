{#- Euclidean distance between two '#rrggbb' colours in RGB space (0 for the
    same colour, 441 for black against white). -#}
{% macro colour_distance(a, b) -%}
sqrt(
    pow(('0x' || substr({{ a }}, 2, 2))::int - ('0x' || substr({{ b }}, 2, 2))::int, 2)
    + pow(('0x' || substr({{ a }}, 4, 2))::int - ('0x' || substr({{ b }}, 4, 2))::int, 2)
    + pow(('0x' || substr({{ a }}, 6, 2))::int - ('0x' || substr({{ b }}, 6, 2))::int, 2)
)
{%- endmacro %}
