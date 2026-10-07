-- Our squad on each snapshot: every player the managed club's teams list, in
-- the first team when both list him.
select
    squads.snapshot_date,
    squads.player_tid as tid,
    arg_min(
        squads.team_tid, squads.team_type is distinct from 'first'
    ) as team_tid
from {{ ref('int_team_squads') }} as squads
inner join {{ ref('stg_career') }} as career
    on squads.club_tid = career.managed_club_tid
group by squads.snapshot_date, squads.player_tid
