-- mart.player_development on the new layers: how far a player is from his
-- ceiling, as a word (the ability itself never leaves the store).
select
    players.season,
    players.phase,
    players.snap_ix,
    players.tid,
    players.person_id,
    players.name,
    players.club_tid,
    players.club,
    case
        when facts.ca >= 0.97 * greatest(facts.pa, facts.ca) then 'At his ceiling'
        when facts.ca >= 0.90 * greatest(facts.pa, facts.ca) then 'Nearly there'
        when facts.ca >= 0.75 * greatest(facts.pa, facts.ca) then 'Developing'
        else 'Lots to come'
    end as development
from {{ ref('site_player_snapshots') }} as players
inner join {{ ref('fact_player_snapshot') }} as facts
    on
        players.person_id = facts.person_id
        and players.phase_date = facts.snapshot_date
where facts.ca is not null and facts.pa is not null
