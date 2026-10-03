-- mart.player_value_est on the new layers: each player's transfer value as the
-- model estimates it (int.player_value, whose coefficients are the raw seed
-- and whose league reputation is the first team's for a reserve side), beside
-- the value the save states where it states one.
select
    players.season,
    players.phase,
    players.snap_ix,
    players.tid,
    players.person_id,
    players.name,
    players.club,
    players.club_tid,
    players.age,
    players.player_value as value_actual,
    round(valuation.value_estimate) as value_est,
    coalesce(players.player_value, round(valuation.value_estimate))
        as value_gbp,
    players.player_value is not null as is_actual,
    valuation.is_in_trusted_band as in_trusted_band
from {{ ref('site_player_snapshots') }} as players
inner join {{ ref('int_player_value') }} as valuation
    on
        players.phase_date = valuation.snapshot_date
        and players.tid = valuation.tid
where valuation.value_estimate is not null
