-- Each person's name on each snapshot. The common name is the one the game
-- displays when a person has one, and is often not a shortening of the legal
-- name at all ('Tite' for Adenor Leonardo Bachi), so it comes first; otherwise
-- first + last, NULL when either is missing.
select
    record.snapshot_date,
    record.tid,
    first_names.name as first_name,
    surnames.name as last_name,
    nicknames.name as common_name,
    coalesce(
        nicknames.name, first_names.name || ' ' || surnames.name
    ) as name
from {{ ref('stg_person_records') }} as record
{{ name_join('first_names', 'first_name_id') }}
{{ name_join('surnames', 'last_name_id') }}
{{ name_join('nicknames', 'common_name_id') }}
