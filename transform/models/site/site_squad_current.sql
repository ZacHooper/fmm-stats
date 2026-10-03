-- mart.squad_current on the new layers: our squad on the newest snapshot, from
-- our teams' squad arrays (site.club_roster), with when each player's first
-- spell with us began.
with latest as (
    select
        season,
        phase
    from {{ ref('site_snapshots') }}
    qualify snap_ix = max(snap_ix) over ()
),

first_spells as (
    select
        person_id,
        min(valid_from) as valid_from
    from {{ ref('site_player_spells') }}
    where spell_type in ('at_club', 'loan_in')
    group by person_id
)

select
    roster.person_id,
    roster.tid,
    roster.name,
    roster.club_tid,
    roster.on_loan_in as is_loan_in,
    roster.club_tid in (select r.club_tid from {{ ref('site_reserve_clubs') }} as r)
        as is_reserve,
    first_spells.valid_from,
    roster.phase_date as as_of
from {{ ref('site_club_roster') }} as roster
inner join latest
    on roster.season = latest.season and roster.phase = latest.phase
left join first_spells
    on roster.person_id = first_spells.person_id
where roster.club_tid in (select o.club_tid from {{ ref('site_our_clubs') }} as o)
