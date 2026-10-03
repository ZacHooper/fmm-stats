-- mart.club_leagues on the new layers: each team's league as at each snapshot
-- (int.team_leagues: the newest league its record named on or before it, as
-- the old view reads it), with the league's name, type and nation
-- (dim_competition, dim_nation) and its reputation that snapshot.
select
    snapshots.season,
    snapshots.phase,
    snapshots.snap_ix,
    leagues.team_tid as club_tid,
    leagues.league_cid,
    competitions.name as league_name,
    nations.name as nation,
    leagues.league_reputation,
    competitions.type as league_type
from {{ ref('int_team_leagues') }} as leagues
inner join {{ ref('site_snapshots') }} as snapshots
    on leagues.snapshot_date = snapshots.phase_date
left join {{ ref('dim_competition') }} as competitions
    on leagues.league_cid = competitions.cid
left join {{ ref('dim_nation') }} as nations
    on competitions.nation_id = nations.nation_id
