-- Each club's own record, one row per club per snapshot. A u16 id field holds
-- var('no_id16') (0xFFFF) for "none"; here every such field reads NULL
-- instead. league_cid is the club's league: league_id, unless the record names
-- another division in other_division (0xFFFF when league_id is the club's own
-- league) or league_id is 0.
{%- set no_id = var('no_id16') %}

select
    cast(phase as date) as snapshot_date,
    tid,
    based_id,
    nation_id,
    colours,
    kits,
    status,
    academy,
    facilities,
    att_avg,
    att_min,
    att_max,
    reserves,
    case
        when other_division = {{ no_id }} and league_id not in (0, {{ no_id }})
            then league_id
    end as league_cid,
    nullif(other_division, {{ no_id }}) as other_division_cid,
    other_last_position,
    nullif(stadium_id, {{ no_id }}) as stadium_id,
    nullif(last_league, {{ no_id }}) as last_league_cid,
    league_pos,
    reputation,
    club_type,
    main_club_tid,
    squad_size,
    staff_size
from {{ source('raw', 'club_details') }}
