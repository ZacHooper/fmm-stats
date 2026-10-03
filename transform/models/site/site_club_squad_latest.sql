-- mart.club_squad_latest on the new layers: every club's squad on the newest
-- snapshot, ours from the squad arrays (site.squad_current), every other
-- club's from the spells (site.snapshot_squad). source is the old view's
-- column name, a keyword kept as it is.
with latest as (
    select
        season,
        phase,
        phase_date
    from {{ ref('site_snapshots') }}
    qualify snap_ix = max(snap_ix) over ()
)

select
    latest.season,
    latest.phase,
    latest.phase_date,
    current_squad.club_tid,
    current_squad.person_id,
    current_squad.tid,
    current_squad.name,
    current_squad.is_loan_in,
    'squad_array' as source  -- noqa: RF04
from {{ ref('site_squad_current') }} as current_squad
cross join latest
union all
select
    squad.season,
    squad.phase,
    squad.phase_date,
    squad.club_tid,
    squad.person_id,
    squad.tid,
    squad.name,
    squad.is_loan_in,
    'spells' as source  -- noqa: RF04
from {{ ref('site_snapshot_squad') }} as squad
inner join latest
    on squad.season = latest.season and squad.phase = latest.phase
where
    squad.club_tid not in (
        select o.club_tid from {{ ref('site_our_clubs') }} as o
    )
