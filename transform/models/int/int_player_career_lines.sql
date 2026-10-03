-- Every career-history line each person has held in any snapshot, once:
-- keyed (person_id, line_index), line_index counting from the oldest line any
-- snapshot holds (0). The game keeps a player's newest lines and drops his
-- oldest as it adds new ones, so each snapshot holds a run of his lines whose
-- seq restarts at -1 on the oldest it kept; it also removes a loan year's
-- 0-app parent-club line once the season is over; and a person who stops
-- being a player (retires, or turns to coaching) loses them all. So the
-- newest snapshot holding a person gives all his lines, and each older one
-- the lines its successor dropped from the front: those before the
-- successor's oldest line, found among its own by the same season, club, fee
-- code and apps (else the same season, club and fee code, for a season still
-- being played; else the same season and club; else after all of them).
-- Each line's figures are from the latest snapshot holding it. Lines are in
-- the save's order, which is not always season order (a contract that ran out
-- can be followed by the next club's line for the season before).

with lines as (
    select
        history.*,
        people.person_id
    from {{ ref('stg_player_history_seasons') }} as history
    inner join {{ ref('int_person_snapshots') }} as people
        on
            history.snapshot_date = people.snapshot_date
            and history.tid = people.tid
),

runs as (
    select
        person_id,
        snapshot_date,
        max(seq) as last_seq,
        lag(snapshot_date) over (
            partition by person_id order by snapshot_date
        ) as previous_date,
        lead(snapshot_date) over (
            partition by person_id order by snapshot_date
        ) as next_date
    from lines
    group by person_id, snapshot_date
),

oldest as (
    select
        runs.person_id,
        runs.snapshot_date,
        runs.previous_date,
        lines.season,
        lines.club_tid,
        lines.fee_code,
        lines.apps
    from runs
    inner join lines
        on
            runs.person_id = lines.person_id
            and runs.snapshot_date = lines.snapshot_date
            and lines.seq = -1
    where runs.previous_date is not null
),

-- where each snapshot's oldest line sits among the previous snapshot's, by
-- the closest of the three matches
placed as (
    select
        oldest.person_id,
        oldest.previous_date as snapshot_date,
        coalesce(
            min(previous.seq) filter (
                where
                previous.fee_code = oldest.fee_code
                and previous.apps = oldest.apps
            ),
            min(previous.seq) filter (
                where previous.fee_code = oldest.fee_code
            ),
            min(previous.seq),
            any_value(previous_run.last_seq) + 1
        ) as kept_from_seq
    from oldest
    inner join runs as previous_run
        on
            oldest.person_id = previous_run.person_id
            and oldest.previous_date = previous_run.snapshot_date
    left join lines as previous
        on
            oldest.person_id = previous.person_id
            and oldest.previous_date = previous.snapshot_date
            and oldest.season = previous.season
            and oldest.club_tid is not distinct from previous.club_tid
    group by oldest.person_id, oldest.previous_date
),

-- each snapshot's lines that no later snapshot holds
kept as (
    select lines.*
    from lines
    inner join runs
        on
            lines.person_id = runs.person_id
            and lines.snapshot_date = runs.snapshot_date
    left join placed
        on
            lines.person_id = placed.person_id
            and lines.snapshot_date = placed.snapshot_date
    where runs.next_date is null or lines.seq < placed.kept_from_seq
)

select
    person_id,
    row_number() over (
        partition by person_id order by snapshot_date, seq
    ) - 1 as line_index,
    tid,
    season,
    club_tid,
    fee_kind,
    fee_gbp,
    apps,
    goals,
    assists,
    rating,
    yellows,
    reds,
    snapshot_date as last_seen_date
from kept
