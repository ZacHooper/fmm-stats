-- The languages each nation speaks, with how well (proficiency 0-100), as
-- stored. A nation can list a language more than once: Iceland lists English
-- at 50, 70 and 95, German and Danish at 50 and 70.
select
    cast(phase as date) as snapshot_date,
    nation_id,
    language_id,
    proficiency
from {{ source('raw', 'nation_languages') }}
