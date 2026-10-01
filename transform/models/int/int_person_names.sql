-- Each person's display name. The common name is the one the game displays
-- when a person has one, and is often not a shortening of the legal name at
-- all ('Tite' for Adenor Leonardo Bachi), so it comes first; otherwise first +
-- last, NULL when either is missing. A store loaded before extract handed over
-- the name ids keeps the resolved name in raw.players_raw.name; it stands in
-- for a snapshot with no ids.
{%- set legacy = 'name' in column_names(source('raw', 'players_raw')) %}

select
    record.season,
    record.phase,
    record.tid,
    record.first_name_id,
    record.last_name_id,
    record.common_name_id,
    first_names.name as first_name,
    surnames.name as last_name,
    nicknames.name as common_name,
    coalesce(
        nicknames.name,
        first_names.name || ' ' || surnames.name
        {%- if legacy %},
        record.name
        {%- endif %}
    ) as name
from {{ source('raw', 'players_raw') }} as record
{{ name_join('first_names', 'first_name_id') }}
{{ name_join('surnames', 'last_name_id') }}
{{ name_join('nicknames', 'common_name_id') }}
