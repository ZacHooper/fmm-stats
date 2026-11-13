-- Every stored team of the period (Team of the Week, Team of the Year, Dream
-- Team ...), its 11 players per snapshot in stored order (slot 1 to 11): each
-- one's tid and name ids as they were, his club then (NULL for none) and the
-- rating that earned the place.
select
    cast(phase as date) as snapshot_date,
    award_id,
    cast(edition_date as date) as edition_date,
    slot,
    cast(nullif(person_tid, {{ var('no_id32') }}) as integer) as person_tid,
    nullif(first_name_id, {{ var('no_id32') }}) as first_name_id,
    nullif(last_name_id, {{ var('no_id32') }}) as last_name_id,
    nullif(common_name_id, {{ var('no_id32') }}) as common_name_id,
    cast(nullif(club_tid, {{ var('no_id32') }}) as integer) as club_tid,
    case
        when person_tid != {{ var('no_id32') }} then rating
    end as rating
from {{ source('raw', 'award_team_places') }}
