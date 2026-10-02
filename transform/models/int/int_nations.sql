-- Each nation once, as its latest snapshot gives it, with the languages it
-- speaks as a list (language and proficiency 0-100, best first). The save
-- lists some languages more than once at different proficiencies (Iceland:
-- English at 50, 70 and 95); the highest is kept.
with latest as (
    {{ latest(ref('stg_nations'), 'nation_id') }}
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
    latest.nation_id,
    latest.name,
    latest.nationality,
    latest.code,
    latest.continent_id,
    latest.capital_city_id,
    latest.national_stadium_id,
    latest.rival_nation_id,
    coalesce(languages.languages, []) as languages,
    latest.last_seen_date
from latest
left join languages
    on
        latest.last_seen_date = languages.snapshot_date
        and latest.nation_id = languages.nation_id
