-- Each move in fact_transfer changes club, except a graduation (an academy
-- into its own club's senior side), which is the only move from a club to
-- itself. fee_gbp is NULL exactly where the fee code is not understood;
-- transfer_type is 'permanent' exactly for a fee above 0 and 'free' exactly
-- for 0. A move the store watched lies between its two snapshots, and a
-- move_date lies inside that gap. Fewer than 5% of moves between two clubs
-- have no readable fee.
with transfers as (
    select * from {{ ref('fact_transfer') }}
),

unreadable as (
    select
        count(*) filter (where fee_kind = 'unknown') * 1.0
        / nullif(count(*), 0) as share
    from transfers
    where transfer_type is distinct from 'graduation'
)

select
    'a move to the same club that is not a graduation' as check,  -- noqa: RF04
    person_id,
    to_line_index
from transfers
where
    coalesce(from_club_tid = to_club_tid, false)
    <> coalesce(transfer_type = 'graduation', false)
union all
select
    'fee_gbp NULL disagrees with fee_kind' as check,  -- noqa: RF04
    person_id,
    to_line_index
from transfers
where (fee_gbp is null) <> (fee_kind = 'unknown')
union all
select
    'transfer_type disagrees with the fee' as check,  -- noqa: RF04
    person_id,
    to_line_index
from transfers
where
    coalesce(transfer_type = 'permanent', false)
    <> coalesce(fee_gbp > 0, false)
    or coalesce(transfer_type = 'free', false)
    <> coalesce(fee_gbp = 0, false)
union all
select
    'a move outside its snapshot gap' as check,  -- noqa: RF04
    person_id,
    to_line_index
from transfers
where
    moved_by <= moved_after
    or (moved_after is null) <> (moved_by is null)
    or move_date <= moved_after
    or move_date > moved_by
union all
select
    '5% or more of club-to-club moves have no fee' as check,  -- noqa: RF04
    null as person_id,
    null as to_line_index
from unreadable
where unreadable.share >= 0.05
