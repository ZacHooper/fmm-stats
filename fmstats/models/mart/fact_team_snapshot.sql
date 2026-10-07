-- Each team on each snapshot: what each side holds on its own (reputation,
-- status, training and youth facilities, league, last season's finish,
-- ground).
select
    team_tid,
    snapshot_date,
    club_tid,
    reputation,
    status,
    training_facilities,
    youth_facilities,
    league_cid,
    other_division_cid,
    last_league_cid,
    last_league_position,
    stadium_id,
    squad_size,
    staff_size,
    is_current
from {{ ref('int_team_snapshots') }}
order by team_tid, snapshot_date
