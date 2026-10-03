{#- The season (the campaign's end year) a date falls in: on or after the
    career's rollover day it is the next year's. `career` is a relation
    alias with stg_career's rollover_month and rollover_day. -#}
{% macro season_of(date, career='career') -%}
(
    year({{ date }})
    + case
        when
            (month({{ date }}), day({{ date }}))
            >= ({{ career }}.rollover_month, {{ career }}.rollover_day)
            then 1
        else 0
    end
)
{%- endmacro %}

{#- The first and last day of a season, by the career's rollover day. -#}
{% macro season_start(season, career='career') -%}
make_date(
    cast({{ season }} as integer) - 1,
    {{ career }}.rollover_month,
    {{ career }}.rollover_day
)
{%- endmacro %}

{% macro season_end(season, career='career') -%}
cast(
    make_date(
        cast({{ season }} as integer),
        {{ career }}.rollover_month,
        {{ career }}.rollover_day
    ) - interval 1 day as date
)
{%- endmacro %}
