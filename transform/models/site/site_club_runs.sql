-- mart.club_runs on the new layers: each person's runs of consecutive player
-- snapshots on one team's books (fact_player_snapshot.team_tid), a run also
-- breaking where he turns into, or stops being, a loanee in our squad (a
-- squad_membership loan-in listing by our club).
with loans_in as (
    select distinct
        person_id,
        snapshot_date
    from {{ ref('squad_membership') }}
    where is_loan_in and is_managed_club
),

held as (
    select
        player.tid,
        player.person_id,
        people.name,
        player.team_tid as club_tid,
        teams.name as club,
        loans_in.person_id is not null as loaned_in,
        snapshots.season,
        snapshots.snap_ix,
        snapshots.phase_date
    from {{ ref('fact_player_snapshot') }} as player
    inner join {{ ref('site_snapshots') }} as snapshots
        on player.snapshot_date = snapshots.phase_date
    inner join {{ ref('dim_person') }} as people
        on player.person_id = people.person_id
    left join {{ ref('dim_team') }} as teams
        on player.team_tid = teams.team_tid
    left join loans_in
        on
            player.person_id = loans_in.person_id
            and player.snapshot_date = loans_in.snapshot_date
),

lagged as (
    select
        *,
        lag(club_tid) over w as previous_club_tid,
        lag(loaned_in) over w as previous_loaned_in
    from held
    window w as (partition by tid, person_id order by snap_ix)
),

grouped as (
    select
        *,
        sum(
            case
                when
                    (club_tid is distinct from previous_club_tid)
                    or (loaned_in is distinct from previous_loaned_in)
                    then 1
                else 0
            end
        ) over (partition by tid, person_id order by snap_ix) as run_id
    from lagged
)

select
    tid,
    person_id,
    any_value(name) as name,
    club_tid,
    any_value(club) as club,
    run_id,
    min(snap_ix) as from_ix,
    max(snap_ix) as to_ix,
    min(season) as season,
    min(phase_date) as from_phase_date,
    bool_or(loaned_in) as ever_loaned_in
from grouped
group by tid, person_id, club_tid, run_id
