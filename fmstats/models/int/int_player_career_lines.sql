-- A table, not a view: it expands every snapshot's history lines (8M rows on
-- Frem's 31 snapshots) to keep 439k, and int_transfers, int_loan_spells,
-- int_team_clubs, dim_person and fact_player_season all read it, int_transfers
-- twice. As a view each read re-ran the expansion: int_transfers took 15 s
-- with it and 2.4 s on the table, which builds in under 3 s.
{{ config(materialized='table') }}

-- Every career-history line each player has held in any snapshot, once.
-- Keyed (person_id, line_index); line_index is 0 for his oldest line.
--
-- Why one snapshot is not enough. The game trims a player's history:
--   * at the season rollover, writing the season just ended into its fixed
--     pool of history records, it frees the oldest lines of players who are
--     still playing and reuses them (Raheem Sterling's Liverpool seasons
--     are gone from his in-game Player History, and so is his first season
--     at Man City, whose record holds a Liege player's 2026/27 line from the
--     2027-07-02 save on);
--   * it removes a loan year's 0-app parent-club line once that season ends;
--   * it drops all his lines when he stops being a player (retires, or
--     turns to coaching).
-- So an older snapshot can hold lines a newer one has lost.
--
-- The rule. The newest snapshot holding a person gives all his lines. Each
-- older snapshot adds only the lines its successor dropped from the front:
-- those before the line the successor starts with. Each line's figures come
-- from the latest snapshot holding it. One person, season and club per line:
--
--   snapshot      lines it holds, oldest first
--   2021-06-27    2010 A  2011 A  2012 B*
--   2023-07-02            2011 A  2012 B  2013 B'  2013 C
--   2026-06-11                    2012 B           2013 C  2014 B
--                 ------  ------  ------           ------  ------
--   kept          2010 A  2011 A  2012 B           2013 C  2014 B
--   taken from    2021    2023    2026             2026    2026
--
--   * a season in progress in 2021; the newest copy (2026's) has its final apps
--   ' a loan year's parent-club line: 2026 removed it, and it comes after
--     the line 2026 starts with, so it is not added back
--
-- Finding where the successor starts. Its first line is looked up among the
-- older snapshot's lines by season, club, fee code and apps; else by season,
-- club and fee code (a season still being played, whose apps grow); else by
-- season and club. With no match at all, every older line is added.
--
-- A recycled tid. The game gives a retired player's tid to a newgen. Lines
-- are stored by tid, so each snapshot's lines are first joined to the person
-- who held the tid on that snapshot (int.person_snapshots), and the union
-- is per person_id ('<tid>-<dob>'):
--
--   snapshot      tid 9 holds            lines join to
--   2023-07-02    a player born 1993     9-1993-04-27
--   2026-06-11    a newgen born 2008     9-2008-03-01
--
-- The two never share a person_id, so their lines never meet; the retired
-- player's history ends with the last snapshot that held him.
--
-- Lines are in the save's order, which is not always season order: a
-- contract that ran out can be followed by the next club's line for the
-- season before.

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
