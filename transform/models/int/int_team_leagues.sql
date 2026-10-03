-- Each team's league on each snapshot: the newest league its record named on
-- or before that snapshot. A team moving division names none on the rollover
-- day (stg_club_details.other_division_cid), so it is still in the league it
-- played last. league_reputation is that competition's on the snapshot.
with named as (
    select
        snapshot_date,
        tid as team_tid,
        league_cid
    from {{ ref('stg_club_details') }}
    where league_cid is not null
),

as_at as (
    select
        snapshots.snapshot_date,
        named.team_tid,
        arg_max(named.league_cid, named.snapshot_date) as league_cid
    from {{ ref('stg_snapshots') }} as snapshots
    inner join named
        on snapshots.snapshot_date >= named.snapshot_date
    group by snapshots.snapshot_date, named.team_tid
)

select
    as_at.snapshot_date,
    as_at.team_tid,
    as_at.league_cid,
    competitions.reputation as league_reputation
from as_at
left join {{ ref('stg_competitions') }} as competitions
    on
        as_at.snapshot_date = competitions.snapshot_date
        and as_at.league_cid = competitions.cid
