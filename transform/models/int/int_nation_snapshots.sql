-- Each nation on each snapshot: its world ranking, the two histories as lists
-- (oldest first; only European nations have coefficients, the last being the
-- season in progress, which reads 0), and the languages it speaks with
-- proficiency 0-100, best first. The save lists some languages more than once
-- at different proficiencies (Iceland: English at 50, 70 and 95); the highest
-- is kept.
with rankings as (
    select
        snapshot_date,
        nation_id,
        list(ranking order by seq) as ranking_history
    from {{ ref('stg_nation_ranking_history') }}
    group by snapshot_date, nation_id
),

coefficients as (
    select
        snapshot_date,
        nation_id,
        list(coefficient order by seq) as coefficient_history
    from {{ ref('stg_nation_coefficients') }}
    group by snapshot_date, nation_id
),

spoken as (
    select
        spoken.snapshot_date,
        spoken.nation_id,
        languages.name as language_name,
        max(spoken.proficiency) as proficiency
    from {{ ref('stg_nation_languages') }} as spoken
    left join {{ ref('stg_languages') }} as languages
        on
            spoken.snapshot_date = languages.snapshot_date
            and spoken.language_id = languages.language_id
    group by spoken.snapshot_date, spoken.nation_id, languages.name
),

languages as (
    select
        snapshot_date,
        nation_id,
        list(
            struct_pack(language := language_name, proficiency := proficiency)
            order by proficiency desc, language_name asc
        ) as languages
    from spoken
    group by snapshot_date, nation_id
)

select
    nations.snapshot_date,
    nations.nation_id,
    nations.is_ranked,
    nations.world_ranking,
    nations.ranking_points,
    coalesce(rankings.ranking_history, []) as ranking_history,
    coalesce(coefficients.coefficient_history, []) as coefficient_history,
    coalesce(languages.languages, []) as languages,
    nations.snapshot_date = max(nations.snapshot_date) over () as is_current
from {{ ref('stg_nations') }} as nations
left join rankings
    on
        nations.snapshot_date = rankings.snapshot_date
        and nations.nation_id = rankings.nation_id
left join coefficients
    on
        nations.snapshot_date = coefficients.snapshot_date
        and nations.nation_id = coefficients.nation_id
left join languages
    on
        nations.snapshot_date = languages.snapshot_date
        and nations.nation_id = languages.nation_id
