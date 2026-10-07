-- Every permanent move between clubs a player's career history shows, and
-- every graduation from a youth side, keyed (person_id, to_line_index): one
-- row per club change between two of his lines (int.player_career_lines), at
-- club level (a team's lines count for the club that owns it, so first team
-- <-> reserves is no move).
--
-- Which lines. A loan line (fee code 'loan', on the borrowing club's line) is
-- a loan, not a move: loan lines are skipped, and a club change across them is
-- a move only if the player ends at a different club (a loan made permanent
-- is a move to the borrowing club). A line with no club (the game's Free
-- agent) is a spell without a club: a move into it is a release, not a
-- transfer, and the move out of it is a free agent signing (from_club_tid
-- NULL).
--
-- Youth sides. A club's academy is a team with no club record whose tid is the
-- u16 complement of its club's (int.team_clubs: Frem 346 -> "Frem Yth" 65189),
-- on its products' first line with a fee code not understood. A youth line
-- counts for its club, with youth_team_tid naming the academy. The move out of
-- it into the club's own senior side is a graduation (transfer_type
-- 'graduation', no fee; from and to club the same); out of it to another club,
-- a move from the academy's club. A first line at a tid that is neither a team
-- nor an academy (a club the save holds no record for) keeps its tid.
--
-- A move made during a season has no line for the buying club until the
-- season ends, so each player's history ends with his club on his newest
-- snapshot (to_line_index one past his last line, is_from_snapshot): where it
-- differs from his last line's club, that is a move too.
--
-- The fee is the code on the selling club's line, the last line before the
-- move (stg_player_history_seasons): fee_gbp where it is a fee, 0 for a free
-- move ('free', 'stay' (a Bosman), a contract that ran out, or a free agent
-- signed), NULL for a code not understood. transfer_type is 'permanent' with a
-- fee above 0, 'free' with 0, NULL otherwise.
--
-- season is the season of the buying club's first line, as the game labels
-- it: a player whose contract ran out in June and who signed in July carries
-- the season just ended. A move seen only on a snapshot takes the season of
-- its move_date, else the snapshot's.
--
-- Snapshot bounds. A move made while the store was watching shows on the
-- player's snapshots as a club change: moved_after is the last snapshot with
-- him elsewhere (or a free agent), moved_by the first at the buying club.
-- move_date is the date his record says he joined the club, where it lies
-- between the two (it does on every club change measured) and is the move's
-- own: the game resets the joined date when a player returns from a loan
-- (confirmed in game on Matteo Grosso, Ruben Minerba and Frederik
-- Ellegaard), so it is NULL where the buying club loaned him out between the
-- move's season and that date, or the date lies more than a season from the
-- move's season. was_free_agent:
-- he had no club on moved_after. The history often has no line for that
-- spell (a contract that ran out in June, a signing in July), so from_club_tid
-- is then the club whose contract ran out. Each club change
-- belongs to the latest move to that club whose season lies within one of the
-- two snapshots' seasons, no later than the later snapshot's where one is (a
-- player can return to the club after it: Aitor Ruibal, 1013 -> Espanyol in
-- 2022/23, back at Espanyol in 2024/25); a move made before the store's first
-- snapshot, or a move undone between two snapshots (A -> B -> A), has none.
with career as (
    select * from {{ ref('stg_career') }}
),

history as (
    select
        career_lines.person_id,
        career_lines.line_index,
        career_lines.season,
        coalesce(teams.club_tid, career_lines.club_tid) as club_tid,
        career_lines.fee_kind,
        career_lines.fee_gbp,
        case
            when teams.is_youth_side then career_lines.club_tid
        end as youth_team_tid
    from {{ ref('int_player_career_lines') }} as career_lines
    left join {{ ref('int_team_clubs') }} as teams
        on career_lines.club_tid = teams.team_tid
    where career_lines.fee_kind is distinct from 'loan'
),

snapshots as (
    select
        player.person_id,
        player.snapshot_date,
        snapshots.season,
        coalesce(owners.club_tid, player.club_tid) as club_tid,
        player.joined_date
    from {{ ref('int_player_info') }} as player
    inner join {{ ref('stg_snapshots') }} as snapshots
        on player.snapshot_date = snapshots.snapshot_date
    left join {{ ref('int_teams') }} as owners
        on
            player.snapshot_date = owners.snapshot_date
            and player.club_tid = owners.team_tid
),

-- each club change between two consecutive snapshots of a player
changes as (
    select
        *,
        case
            when joined_date > moved_after and joined_date <= moved_by
                then joined_date
        end as move_date
    from (
        select
            person_id,
            lag(snapshot_date) over w as moved_after,
            lag(season) over w as season_after,
            snapshot_date as moved_by,
            season as season_by,
            lag(club_tid) over w as from_club_tid,
            club_tid as to_club_tid,
            joined_date
        from snapshots
        window w as (partition by person_id order by snapshot_date)
    ) as steps
    where
        moved_after is not null
        and from_club_tid is distinct from to_club_tid
        and to_club_tid is not null
),

last_lines as (
    select
        person_id,
        max(line_index) as line_index
    from {{ ref('int_player_career_lines') }}
    group by person_id
),

-- his club on his newest snapshot, after his last line
newest as (
    select
        snapshots.person_id,
        last_line.line_index + 1 as line_index,
        coalesce(
            {{ season_of('changes.move_date') }}, snapshots.season
        ) as season,
        snapshots.club_tid,
        cast(null as varchar) as fee_kind,
        cast(null as bigint) as fee_gbp,
        cast(null as integer) as youth_team_tid
    from snapshots
    inner join last_lines as last_line
        on snapshots.person_id = last_line.person_id
    left join changes
        on
            snapshots.person_id = changes.person_id
            and snapshots.snapshot_date = changes.moved_by
    cross join career
    qualify
        snapshots.snapshot_date
        = max(snapshots.snapshot_date) over (partition by snapshots.person_id)
),

steps as (
    select
        *,
        false as is_from_snapshot
    from history
    union all
    select
        *,
        true as is_from_snapshot
    from newest
),

moves as (
    select *
    from (
        select
            person_id,
            line_index as from_line_index,
            club_tid as from_club_tid,
            youth_team_tid,
            fee_kind,
            fee_gbp,
            lead(line_index) over w as to_line_index,
            lead(club_tid) over w as to_club_tid,
            lead(season) over w as season,
            lead(is_from_snapshot) over w as is_from_snapshot
        from steps
        window w as (partition by person_id order by line_index)
    ) as pairs
    where
        to_line_index is not null
        and to_club_tid is not null
        and (
            youth_team_tid is not null
            or from_club_tid is distinct from to_club_tid
        )
),

-- each club change, the move it shows: the latest move to that club whose
-- season is no later than the later snapshot's, else one a season later (a
-- signing in June for the season to come), so a later return to the club is
-- not taken for it
placed as (
    select
        changes.person_id,
        changes.moved_after,
        changes.moved_by,
        changes.move_date,
        changes.from_club_tid is null as was_free_agent,
        coalesce(
            max(moves.to_line_index) filter (
                where moves.season <= changes.season_by
            ),
            max(moves.to_line_index)
        ) as to_line_index
    from changes
    inner join moves
        on
            changes.person_id = moves.person_id
            and changes.to_club_tid = moves.to_club_tid
            and moves.season
            between changes.season_after - 1 and changes.season_by + 1
    group by all
),

-- one club change per move: the earliest, should two find the same move
bounded as (
    select *
    from placed
    qualify
        row_number() over (
            partition by person_id, to_line_index order by moved_by
        ) = 1
),

-- moves after which the buying club loaned the player out, up to the season
-- of the date his record says he joined it
loaned_between as (
    select distinct
        moves.person_id,
        moves.to_line_index
    from moves
    inner join bounded
        on
            moves.person_id = bounded.person_id
            and moves.to_line_index = bounded.to_line_index
    cross join career
    inner join {{ ref('int_loan_spells') }} as loans
        on
            moves.person_id = loans.person_id
            and moves.to_club_tid = loans.parent_club_tid
            and loans.season
            between moves.season and {{ season_of('bounded.move_date') }}
)

select
    moves.person_id,
    moves.to_line_index,
    moves.from_line_index,
    moves.from_club_tid,
    moves.youth_team_tid,
    moves.to_club_tid,
    moves.season,
    bounded.moved_after,
    bounded.moved_by,
    case
        when
            {{ season_of('bounded.move_date') }}
            between moves.season - 1 and moves.season + 1
            and loaned_between.person_id is null
            then bounded.move_date
    end as move_date,
    bounded.was_free_agent,
    moves.fee_kind,
    case
        when moves.youth_team_tid is not null then null
        when moves.from_club_tid is null then 0
        when moves.fee_kind = 'fee' then moves.fee_gbp
        when moves.fee_kind in ('free', 'stay', 'contract_ended') then 0
    end as fee_gbp,
    case
        when
            moves.youth_team_tid is not null
            and moves.from_club_tid = moves.to_club_tid
            then 'graduation'
        when moves.from_club_tid is null then 'free'
        when moves.fee_kind = 'fee' and moves.fee_gbp > 0 then 'permanent'
        when moves.fee_kind = 'fee' then 'free'
        when moves.fee_kind in ('free', 'stay', 'contract_ended') then 'free'
    end as transfer_type,
    moves.is_from_snapshot
from moves
left join bounded
    on
        moves.person_id = bounded.person_id
        and moves.to_line_index = bounded.to_line_index
left join loaned_between
    on
        moves.person_id = loaned_between.person_id
        and moves.to_line_index = loaned_between.to_line_index
cross join career
