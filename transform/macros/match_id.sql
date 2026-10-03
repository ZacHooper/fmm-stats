{#- A match's id: its date and its two teams packed into one BIGINT,
    yyyymmdd * base^2 + home_team_tid * base + away_team_tid, base being
    var('match_id_tid_base') (100000). 2027-07-28, Salzburg (125) at home to
    Frem (346), is 20270728 00125 00346 -> 202707280012500346. A match is
    (match_date, home_team_tid, away_team_tid), so the id is unique, the same in
    every snapshot and every rebuild, sorts by date and reads back by eye.
    dim_match tests that every tid stays below the base. -#}
{% macro match_id(match_date, home_team_tid, away_team_tid) -%}
    {%- set base = var('match_id_tid_base') -%}
    (
        cast(strftime({{ match_date }}, '%Y%m%d') as bigint)
        * {{ base }} * {{ base }}
        + cast({{ home_team_tid }} as bigint) * {{ base }}
        + {{ away_team_tid }}
    )
{%- endmacro %}
