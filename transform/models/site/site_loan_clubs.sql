-- The clubs a player of ours could be loaned to on each snapshot, keyed
-- (snapshot_date, team_tid): every team, ours aside, in our division or the
-- var('loan_outlook').tiers - 1 below it (site.leagues ladder_rank), with the
-- formation its manager prefers where it is one var('formation_slots') lists
-- (NULL otherwise: it plays var('fallback_formation')).
with managers as (
    select
        spells.team_tid,
        snapshots.snapshot_date,
        staff.formation_preferred_name as formation
    from {{ ref('fact_staff_spell') }} as spells
    inner join {{ ref('stg_snapshots') }} as snapshots
        on
            snapshots.snapshot_date
            between spells.first_seen_date and spells.last_seen_date
    inner join {{ ref('fact_staff_snapshot') }} as staff
        on
            spells.person_id = staff.person_id
            and snapshots.snapshot_date = staff.snapshot_date
    where spells.role = 'manager'
)

select
    clubs.snapshot_date,
    clubs.team_tid,
    clubs.league_cid,
    leagues.ladder_rank,
    case
        when
            managers.formation in (
                select slots.formation
                from {{ ref('site_formation_slots') }} as slots
            )
            then managers.formation
    end as formation
from {{ ref('site_clubs') }} as clubs
inner join {{ ref('site_leagues') }} as leagues
    on
        clubs.snapshot_date = leagues.snapshot_date
        and clubs.league_cid = leagues.cid
left join managers
    on
        clubs.snapshot_date = managers.snapshot_date
        and clubs.team_tid = managers.team_tid
where
    leagues.ladder_rank < {{ var('loan_outlook').tiers }}
    and clubs.team_tid not in (
        select ours.team_tid from {{ ref('site_our_teams') }} as ours
    )
