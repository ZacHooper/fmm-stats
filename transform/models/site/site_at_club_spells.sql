-- mart.at_club_spells on the new layers, its rules unchanged: one spell per
-- club run (site.club_runs) that was never a loan in, dated by the window it
-- arrived in (macros/site.sql arrival_window): valid_from is the window's
-- start, no earlier than the day after the snapshot that last showed him
-- elsewhere and no later than the run's first snapshot; valid_to is the day
-- before the next spell, or before the first snapshot that no longer shows
-- him, NULL while the run reaches the newest snapshot. Seasons start on 1
-- July, the old mart's calendar (var('site_calendar')). The first match per club and season is
-- fact_player_match's.
with first_matches as (
    select
        matches.player_tid as tid,
        matches.team_tid,
        {{ season_of('fixtures.match_date') }} as season,
        min(fixtures.match_date) as first_match
    from {{ ref('fact_player_match') }} as matches
    inner join {{ ref('dim_match') }} as fixtures
        on matches.match_id = fixtures.match_id
    cross join {{ site_calendar() }} as career
    where matches.appeared
    group by all
),

lagged as (
    select
        runs.*,
        lag(runs.to_ix) over w as prev_to_ix
    from {{ ref('site_club_runs') }} as runs
    window w as (partition by runs.tid, runs.person_id order by runs.from_ix)
),

r as (
    select
        lagged.*,
        prev_s.phase_date as prev_phase_date,
        after_s.phase_date as after_phase_date,
        first_matches.first_match
    from lagged
    left join {{ ref('site_snapshots') }} as prev_s
        on lagged.prev_to_ix = prev_s.snap_ix
    left join {{ ref('site_snapshots') }} as after_s
        on lagged.to_ix + 1 = after_s.snap_ix
    left join first_matches
        on
            lagged.tid = first_matches.tid
            and lagged.club_tid = first_matches.team_tid
            and lagged.season = first_matches.season
),

w as (
    select
        r.*,
        {{ arrival_window('r') }} as arrival_window,
        r.prev_to_ix is not null as is_transition
    from r
),

dated as (
    select
        w.*,
        case
            when w.is_transition and w.arrival_window = 'winter'
                then least(
                    greatest(
                        {{ winter_cut('w.season') }},
                        coalesce(
                            w.prev_phase_date + 1, {{ winter_cut('w.season') }}
                        )
                    ),
                    w.from_phase_date
                )
            when w.is_transition
                then least(
                    greatest(
                        {{ season_start('w.season') }},
                        coalesce(
                            w.prev_phase_date + 1,
                            {{ season_start('w.season') }}
                        )
                    ),
                    w.from_phase_date
                )
            else w.from_phase_date
        end as valid_from
    from w
    cross join {{ site_calendar() }} as career
)

select
    person_id,
    tid,
    name,
    'at_club' as spell_type,
    club_tid,
    club,
    season,
    valid_from,
    coalesce(
        lead(valid_from) over (partition by tid, person_id order by from_ix),
        after_phase_date
    ) - 1 as valid_to,
    case when is_transition then arrival_window end as arrival_window
from dated
where not ever_loaned_in
