{#- The common name is the one the game displays when a person has one, and is often not a
    shortening of the legal name at all ('Tite' for Adenor Leonardo Bachi), so it comes first;
    otherwise first + last, NULL when either is missing. A store loaded before extract handed
    over the name ids keeps the resolved name in raw.players_raw.name; it stands in for a
    snapshot with no ids. -#}
{%- set legacy = 'name' in column_names(source('raw', 'players_raw')) -%}

SELECT r.season, r.phase, r.tid, r.first_name_id, r.last_name_id, r.common_name_id,
       f.name AS first_name, l.name AS last_name, c.name AS common_name,
       COALESCE(c.name, f.name || ' ' || l.name{{ ', r.name' if legacy }}) AS name
FROM {{ source('raw', 'players_raw') }} r
{{ name_join('f', 'first_names', 'first_name_id') }}
{{ name_join('l', 'surnames', 'last_name_id') }}
{{ name_join('c', 'nicknames', 'common_name_id') }}
