-- Our squad's time at each club inside the home-grown window, keyed
-- (snapshot_date, person_id, club_tid): the months he was registered there
-- between the start of the season he turns 15 and the end of the season he
-- turns 22 (var('home_grown_window_ages'); the rulebook's window ends a
-- season earlier, and the house rule runs it one longer so the birthday does
-- not decide a borderline case), up to the snapshot.
--
-- Two sources, unioned as dated intervals and merged per club before months
-- are counted, since they overlap:
--   * the career history (fact_player_season): each line a season at its
--     team's club (a youth side counts for its club), from one rollover day to
--     the next, a season with several lines split evenly across them in line
--     order, the save storing no transfer date; a loan line credits the
--     borrowing club;
--   * the season in progress, which the history may not hold yet: from the
--     season's start, or the date he joined where that is later, to the
--     snapshot, at the club whose squad lists him (the borrowing club for a
--     loan).
-- last_to is the end of his latest interval there.
with career as (
    select * from {{ ref('stg_career') }}
),

squad as (
    select
        squad.snapshot_date,
        snapshots.season,
        squad.person_id,
        squad.loaned_to_club_tid,
        squad.is_loan_in,
        people.dob,
        players.club_tid,
        players.joined_date,
        {{ season_start(
            season_of('people.dob + interval ' ~ var('home_grown_window_ages')[0]
                ~ ' year')
        ) }} as window_from,
        {{ season_end(
            season_of('people.dob + interval ' ~ var('home_grown_window_ages')[1]
                ~ ' year')
        ) }} as window_to
    from {{ ref('int_our_squad') }} as squad
    cross join career
    inner join {{ ref('stg_snapshots') }} as snapshots
        on squad.snapshot_date = snapshots.snapshot_date
    inner join {{ ref('dim_person') }} as people
        on squad.person_id = people.person_id
    left join {{ ref('fact_player_snapshot') }} as players
        on
            squad.snapshot_date = players.snapshot_date
            and squad.person_id = players.person_id
    where people.dob is not null
),

lines as (
    select
        lines.person_id,
        lines.season,
        coalesce(teams.club_tid, team_clubs.club_tid, lines.team_tid)
            as club_tid,
        row_number() over (
            partition by lines.person_id, lines.season
            order by lines.line_index
        ) as leg,
        count(*) over (partition by lines.person_id, lines.season) as legs
    from {{ ref('fact_player_season') }} as lines
    left join {{ ref('dim_team') }} as teams
        on lines.team_tid = teams.team_tid
    left join {{ ref('int_team_clubs') }} as team_clubs
        on lines.team_tid = team_clubs.team_tid
    where lines.team_tid is not null and lines.season is not null
),

intervals as (
    select
        squad.snapshot_date,
        squad.person_id,
        lines.club_tid,
        {{ season_start('lines.season') }}
        + cast(
            (lines.leg - 1)
            * date_diff(
                'day',
                {{ season_start('lines.season') }},
                {{ season_start('lines.season + 1') }}
            )
            / lines.legs as integer
        ) as from_date,
        {{ season_start('lines.season') }}
        + cast(
            lines.leg
            * date_diff(
                'day',
                {{ season_start('lines.season') }},
                {{ season_start('lines.season + 1') }}
            )
            / lines.legs as integer
        ) as to_date
    from squad
    cross join career
    inner join lines
        on squad.person_id = lines.person_id
    where lines.season <= squad.season
    union all
    select
        squad.snapshot_date,
        squad.person_id,
        case
            when squad.loaned_to_club_tid is not null
                then squad.loaned_to_club_tid
            when squad.is_loan_in then career.managed_club_tid
            else squad.club_tid
        end as club_tid,
        case
            when squad.is_loan_in then {{ season_start('squad.season') }}
            when squad.loaned_to_club_tid is null
                then greatest(
                    {{ season_start('squad.season') }},
                    coalesce(squad.joined_date, {{ season_start('squad.season') }})
                )
            else {{ season_start('squad.season') }}
        end as from_date,
        squad.snapshot_date as to_date
    from squad
    cross join career
    where
        squad.loaned_to_club_tid is not null
        or squad.is_loan_in
        or squad.club_tid is not null
),

clipped as (
    select
        intervals.snapshot_date,
        intervals.person_id,
        intervals.club_tid,
        greatest(intervals.from_date, squad.window_from) as from_date,
        least(intervals.to_date, squad.window_to + 1, squad.snapshot_date)
            as to_date
    from intervals
    inner join squad
        on
            intervals.snapshot_date = squad.snapshot_date
            and intervals.person_id = squad.person_id
),

-- overlapping intervals at one club merged into islands
marked as (
    select
        *,
        case
            when
                previous_end is null or from_date > previous_end
                then 1
            else 0
        end as new_island
    from (
        select
            *,
            max(to_date) over (
                partition by snapshot_date, person_id, club_tid
                order by from_date, to_date
                rows between unbounded preceding and 1 preceding
            ) as previous_end
        from clipped
        where to_date > from_date
    ) as ordered
),

islands as (
    select
        snapshot_date,
        person_id,
        club_tid,
        min(from_date) as from_date,
        max(to_date) as to_date
    from (
        select
            *,
            sum(new_island) over (
                partition by snapshot_date, person_id, club_tid
                order by from_date, to_date
            ) as island
        from marked
    ) as numbered
    group by snapshot_date, person_id, club_tid, island
)

select
    snapshot_date,
    person_id,
    club_tid,
    round(
        sum(date_diff('day', from_date, to_date))
        / {{ var('days_in_month') }},
        1
    ) as months,
    max(to_date) as last_to
from islands
group by snapshot_date, person_id, club_tid
