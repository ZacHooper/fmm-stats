-- Every team's squad array: one row per player listed, in the team's order.
-- National sides are club-shaped and keep their squads here too.
select
    cast(phase as date) as snapshot_date,
    club_tid as team_tid,
    player_tid,
    slot
from {{ source('raw', 'club_squad') }}
