{#- The old mart's fixed season calendar as a relation with the columns the
    season macros read (rollover_month, rollover_day): var('site_calendar'),
    1 July. Cross join it as `career` in a site view. -#}
{% macro site_calendar() -%}
(
    select
        {{ var('site_calendar').month }} as rollover_month,
        {{ var('site_calendar').day }} as rollover_day
)
{%- endmacro %}

{#- The summer/winter cut of a season: 1 January of its end year. Before it is
    the autumn half (the summer window), on or after it the spring half. -#}
{% macro winter_cut(season) -%}
make_date(cast({{ season }} as integer), 1, 1)
{%- endmacro %}

{#- Which window a club run arrived in, in evidence order (mart.at_club_spells'
    rule, fmstats/mart.py _ARRIVAL_WINDOW_SQL): his first match for the club
    before the winter cut; else a snapshot before the cut already showing him
    there; else a first match on or after it; else last seen elsewhere on or
    after it; else summer. `r` has first_match, from_phase_date,
    prev_phase_date and season. -#}
{% macro arrival_window(r='r') -%}
case
    when
        {{ r }}.first_match is not null
        and {{ r }}.first_match < {{ winter_cut(r ~ '.season') }}
        then 'summer'
    when
        {{ r }}.from_phase_date is not null
        and {{ r }}.from_phase_date < {{ winter_cut(r ~ '.season') }}
        then 'summer'
    when {{ r }}.first_match is not null then 'winter'
    when
        {{ r }}.prev_phase_date is not null
        and {{ r }}.prev_phase_date >= {{ winter_cut(r ~ '.season') }}
        then 'winter'
    else 'summer'
end
{%- endmacro %}

{#- The site schema's table macros, which a dbt model cannot be: run after
    the build (on-run-end in dbt_project.yml). site.squad_on(d) is
    mart.squad_on: who was ours on a date, from site.player_spells. -#}
{% macro create_site_macros() -%}
{% if execute and adapter.get_relation(
    database=target.database, schema='site', identifier='player_spells') %}
create or replace macro site.squad_on(d) as table
select
    s.person_id,
    s.tid,
    s.name,
    s.club_tid,
    s.spell_type,
    s.valid_from,
    s.valid_to
from site.player_spells as s
where
    s.spell_type in ('at_club', 'loan_in')
    and s.club_tid in (select o.club_tid from site.our_clubs as o)
    and cast(d as date) >= s.valid_from
    and (s.valid_to is null or cast(d as date) <= s.valid_to)
{% endif %}
{%- endmacro %}
