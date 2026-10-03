-- Who is in each team's squad on each snapshot: one row per person a team's
-- squad array lists, keyed (person_id, snapshot_date, team_tid). The squad
-- array is membership; a player's own record names the team whose books he is
-- on (ownership), and the two disagree for a loanee, who is listed by the
-- borrowing team while his record names his parent team. A lapsed loan can
-- leave a departed player's record naming our club, so "who is in a squad"
-- is answered here, never by the record's club.
--
-- is_loan_in: the listing team's club is not the club that owns the team on
-- his record. A player's parent team can list him too for a while after he is
-- loaned out, so one person can be in two squads on one snapshot.
-- is_managed_club: the team belongs to the club the career manages.
with listed as (
    select
        people.person_id,
        squads.snapshot_date,
        squads.team_tid,
        squads.club_tid,
        squads.team_type,
        squads.slot,
        squads.player_tid as tid,
        person.club_tid as record_team_tid,
        coalesce(owners.club_tid, person.club_tid) as record_club_tid
    from {{ ref('int_team_squads') }} as squads
    inner join {{ ref('int_person_snapshots') }} as people
        on
            squads.snapshot_date = people.snapshot_date
            and squads.player_tid = people.tid
    inner join {{ ref('stg_persons') }} as person
        on
            squads.snapshot_date = person.snapshot_date
            and squads.player_tid = person.tid
    left join {{ ref('int_teams') }} as owners
        on
            person.snapshot_date = owners.snapshot_date
            and person.club_tid = owners.team_tid
)

select
    listed.*,
    (listed.record_club_tid is distinct from listed.club_tid) as is_loan_in,
    listed.club_tid = career.managed_club_tid as is_managed_club
from listed
cross join {{ ref('stg_career') }} as career
