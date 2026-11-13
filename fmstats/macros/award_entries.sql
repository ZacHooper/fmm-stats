{#- Every edition of an award the store has seen, from `relation` (an stg award
    table, one row per place per snapshot), with `position` its place column and
    `value` the score or rating a place carries.
    A weekly or monthly award keeps only the current season's editions, so an
    edition is read from the newest snapshot that still holds it and survives
    in the store after the game drops it. Unfilled places are dropped.
    name: as the edition stores it (the name ids the game wrote then), so a
    retired winner keeps his name after his tid goes to a newgen.
    person_id: the person with the entry's tid and the same name ids on some
    snapshot, the newest one; NULL for a winner no snapshot holds (he left the
    database before the first save).
    season: an annual award's edition year (the season the award screen shows:
    2026 for the 2025/26 Premier League's), and the career's season of the
    edition's date for a weekly or monthly award. -#}
{% macro award_entries(relation, position, value) -%}
with record as (
    select *
    from {{ relation }}
    where person_tid is not null
    qualify snapshot_date = max(snapshot_date) over (
        partition by award_id, edition_date
    )
),

career as (
    select * from {{ ref('stg_career') }}
),

named as (
    select
        record.*,
        coalesce(
            nicknames.name, first_names.name || ' ' || surnames.name
        ) as name
    from record
    {{ name_join('first_names', 'first_name_id') }}
    {{ name_join('surnames', 'last_name_id') }}
    {{ name_join('nicknames', 'common_name_id') }}
),

identified as (
    select
        named.*,
        {{ person_id('persons.tid', 'persons.dob') }} as person_id,
        persons.tid is not null as is_identified
    from named
    left join {{ ref('stg_persons') }} as persons
        on
            named.person_tid = persons.tid
            and named.first_name_id is not distinct from persons.first_name_id
            and named.last_name_id is not distinct from persons.last_name_id
            and named.common_name_id is not distinct from nullif(
                persons.common_name_id, {{ var('no_id32') }}
            )
    qualify row_number() over (
        partition by named.award_id, named.edition_date, named.{{ position }}
        order by persons.snapshot_date desc nulls last
    ) = 1
)

select
    identified.award_id,
    identified.edition_date,
    case
        when awards.period = 'season' then year(identified.edition_date)
        else {{ season_of('identified.edition_date') }}
    end as season,
    identified.{{ position }},
    case when identified.is_identified then identified.person_id end
        as person_id,
    identified.person_tid,
    identified.name,
    identified.club_tid,
    identified.{{ value }},
    identified.snapshot_date as last_seen_date
from identified
inner join {{ ref('int_awards') }} as awards
    on identified.award_id = awards.award_id
cross join career
{%- endmacro %}
