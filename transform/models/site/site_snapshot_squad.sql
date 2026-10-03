-- mart.snapshot_squad on the new layers, its rule unchanged: who was on each
-- club's books on each snapshot date, by the at-club and loan-in spells of
-- site.player_spells covering it.
select
    snapshots.season,
    snapshots.phase,
    snapshots.snap_ix,
    snapshots.phase_date,
    spells.person_id,
    any_value(spells.tid) as tid,
    any_value(spells.name) as name,
    max(spells.club_tid) as club_tid,
    bool_or(spells.spell_type = 'loan_in') as is_loan_in,
    min(spells.valid_from) as valid_from
from {{ ref('site_snapshots') }} as snapshots
inner join {{ ref('site_player_spells') }} as spells
    on
        spells.spell_type in ('at_club', 'loan_in')
        and snapshots.phase_date >= spells.valid_from
        and (spells.valid_to is null or snapshots.phase_date <= spells.valid_to)
group by
    snapshots.season,
    snapshots.phase,
    snapshots.snap_ix,
    snapshots.phase_date,
    spells.person_id
