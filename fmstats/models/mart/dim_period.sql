-- The periods of a match in order, each with the minutes it holds
-- (var('match_periods')); the shoot-out has no minutes.
{%- set periods = var('match_periods') %}
{% for last_minute, period in periods %}
select
    '{{ period }}' as period,
    {{ loop.index }} as period_order,
    {{ 1 if loop.first else periods[loop.index0 - 1][0] + 1 }} as first_minute,
    {{ last_minute }} as last_minute
union all
{% endfor %}
select
    '{{ var("shootout_period") }}' as period,
    {{ periods | length + 1 }} as period_order,
    null as first_minute,
    null as last_minute
