-- A spell left open (to_date NULL, "still there") is one the newest snapshot
-- still shows: an open spell on a team's books has the player on that team's
-- books on the newest snapshot, and an open loan to us has him in our current
-- squad as a loan-in from that parent club. A lapsed loan does not stay open.
with latest as (
    select max(snapshot_date) as snapshot_date
    from {{ ref('stg_snapshots') }}
),

open_spells as (
    select *
    from {{ ref('site_player_spells') }}
    where to_date is null and spell_type in ('at_club', 'loan_in')
)

select
    'open team spell not on newest snapshot' as "check",  -- noqa: RF04
    open_spells.person_id,
    open_spells.spell_type,
    open_spells.club_tid,
    open_spells.from_date
from open_spells
cross join latest
where
    open_spells.spell_type = 'at_club'
    and not exists (
        select 1 as found
        from {{ ref('fact_player_snapshot') }} as players
        where
            players.person_id = open_spells.person_id
            and players.snapshot_date = latest.snapshot_date
            and players.team_tid = open_spells.club_tid
    )
union all
select
    'open loan-in not in current squad' as "check",  -- noqa: RF04
    open_spells.person_id,
    open_spells.spell_type,
    open_spells.club_tid,
    open_spells.from_date
from open_spells
where
    open_spells.spell_type = 'loan_in'
    and not exists (
        select 1 as found
        from {{ ref('mart_squad_membership') }} as squads
        where
            squads.person_id = open_spells.person_id
            and squads.is_current
            and squads.is_managed_club
            and squads.is_loan_in
            and squads.record_club_tid = open_spells.club_tid
    )
