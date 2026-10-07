{#- Age in whole years on a date: the years between the two, less one when the
    birthday has not yet come round that year. -#}
{% macro age_on(dob, on_date) -%}
date_diff('year', {{ dob }}, {{ on_date }})
- case
    when (month({{ on_date }}), day({{ on_date }}))
    < (month({{ dob }}), day({{ dob }})) then 1
    else 0
end
{%- endmacro %}
