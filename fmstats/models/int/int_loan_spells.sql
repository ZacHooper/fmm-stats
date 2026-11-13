-- Every loan the store can see, one row per player, season and borrowing
-- club: keyed (person_id, season, borrowing_club_tid). A loan is a spell on top
-- of an unchanged contract, never a transfer. Three sources:
--   * the loan pool (stg_loans): every loan in the world while it runs, with
--     its agreed start and end, the share of the player's wage the borrowing
--     club pays and the option flag. A loan is a row for each season of a
--     snapshot whose pool holds it;
--   * the career history: a loan line (fee code 'loan') is a season at the
--     borrowing club;
--   * the squads: a club's first, b or reserve team listing a player whose
--     own record names another club's team (int.squad_membership is_loan_in;
--     a national side is not a loan). The history has no line for a loan made
--     during the season until it ends.
-- borrowing_team_tid is the team that lists him, else the pool's or the loan
-- line's team. first_seen_date / last_seen_date are the snapshots listing him
-- there (NULL for a loan no squad lists).
--
-- parent_club_tid, first found of:
--   * his record's club, where a snapshot's pool or squads show him on loan;
--   * the club we manage, where his weeks in Player Progress are flagged on
--     loan in that season (the flag marks only loans out: no run of it
--     overlaps a loan to us on the gate stores);
--   * the club a later snapshot shows him at, where his record's joined date
--     there is before the loan's season began and it is not the borrowing
--     club;
--   * the club of his last line before the loan line that is not a loan.
-- The last rule alone is not enough: the game removes a loan year's 0-app
-- parent-club line once the season ends, so a player who joined a club and
-- went straight out on loan keeps no line there, and the line before the loan
-- names his previous club.
--
-- start_date and end_date are the pool's agreed dates wherever a snapshot's
-- pool holds the loan (a loan of several seasons carries the same dates on
-- each). The day-one database holds a few loans agreed years before it
-- (Truro: one from 2006); the dates are kept as stored. ended_early_by_date
-- is the first snapshot after the pool last held the loan, where that is
-- before its agreed end: the loan ended between the two (recalled, cut
-- short, or turned into a transfer).
--
-- A loan of ours no snapshot's pool holds (one that started and ended between
-- two snapshots) falls back to Player Progress: the first and last week
-- flagged on loan (int.progress_spells), so to the week, and the last flagged
-- week is the save's own on a loan still running. A run of flagged weeks
-- belongs to the loan of the season it starts in, and is cut at a season
-- boundary only where a loan of ours in the next season meets it, since the
-- flag can run unbroken from a loan into its renewal; a loan's last weeks can
-- lie past the rollover day (Bucaspor's run to 28 June, its rollover 20
-- June). With two loans of ours in one season the runs cannot be told apart,
-- so both read NULL. Elsewhere a loan no pool holds has no dates.
with career as (
    select * from {{ ref('stg_career') }}
),

teams as (
    select
        team_tid,
        club_tid
    from {{ ref('int_teams') }}
    qualify
        snapshot_date = max(snapshot_date) over (partition by team_tid)
),

history as (
    select
        career_lines.person_id,
        career_lines.line_index,
        career_lines.season,
        career_lines.club_tid as team_tid,
        coalesce(teams.club_tid, career_lines.club_tid) as club_tid,
        career_lines.fee_kind = 'loan' as is_loan
    from {{ ref('int_player_career_lines') }} as career_lines
    left join teams
        on career_lines.club_tid = teams.team_tid
),

-- each loan line with the club of the last line before it that is not a
-- loan; two loan lines of one season at one club are one loan, the later
-- line's
line_loans as (
    select
        person_id,
        season,
        club_tid as borrowing_club_tid,
        arg_max_null(team_tid, line_index) as borrowing_team_tid,
        arg_max_null(parent_club_tid, line_index) as parent_club_tid
    from (
        select
            *,
            last_value(
                case when not is_loan then club_tid end ignore nulls
            ) over (
                partition by person_id
                order by line_index
                rows between unbounded preceding and 1 preceding
            ) as parent_club_tid
        from history
    ) as parented
    where is_loan and club_tid is not null
    group by person_id, season, club_tid
),

-- each snapshot's loan pool, the player's own record's club his parent; one
-- loan is one (person, borrowing club, start date) across snapshots, its
-- terms as the latest snapshot holds them
pool as (
    select
        people.person_id,
        snapshots.season,
        loans.snapshot_date,
        coalesce(borrowers.club_tid, loans.borrowing_club_tid)
            as borrowing_club_tid,
        loans.borrowing_club_tid as borrowing_team_tid,
        coalesce(parents.club_tid, person.club_tid) as parent_club_tid,
        loans.start_date,
        loans.end_date,
        loans.wage_pct,
        loans.has_option
    from {{ ref('stg_loans') }} as loans
    inner join {{ ref('stg_snapshots') }} as snapshots
        on loans.snapshot_date = snapshots.snapshot_date
    inner join {{ ref('int_person_snapshots') }} as people
        on
            loans.snapshot_date = people.snapshot_date
            and loans.tid = people.tid
    inner join {{ ref('stg_persons') }} as person
        on
            loans.snapshot_date = person.snapshot_date
            and loans.tid = person.tid
    left join {{ ref('int_teams') }} as borrowers
        on
            loans.snapshot_date = borrowers.snapshot_date
            and loans.borrowing_club_tid = borrowers.team_tid
    left join {{ ref('int_teams') }} as parents
        on
            person.snapshot_date = parents.snapshot_date
            and person.club_tid = parents.team_tid
),

-- the snapshot after each one
next_snapshots as (
    select
        snapshot_date,
        lead(snapshot_date) over (order by snapshot_date) as next_date
    from {{ ref('stg_snapshots') }}
),

pool_loans as (
    select
        pool.person_id,
        pool.borrowing_club_tid,
        pool.start_date,
        min(pool.season) as first_season,
        max(pool.season) as last_season,
        arg_max(pool.borrowing_team_tid, pool.snapshot_date)
            as borrowing_team_tid,
        arg_max(pool.parent_club_tid, pool.snapshot_date) as parent_club_tid,
        arg_max(pool.end_date, pool.snapshot_date) as end_date,
        arg_max(pool.wage_pct, pool.snapshot_date) as wage_pct,
        arg_max(pool.has_option, pool.snapshot_date) as has_option,
        max(pool.snapshot_date) as last_pooled_date
    from pool
    group by pool.person_id, pool.borrowing_club_tid, pool.start_date
),

-- each pool loan on each season a snapshot's pool held it; two loans of one
-- season at one club are one loan, the later-starting one's
pooled as (
    select
        pool_loans.person_id,
        seasons.season,
        pool_loans.borrowing_club_tid,
        arg_max(pool_loans.borrowing_team_tid, pool_loans.start_date)
            as borrowing_team_tid,
        arg_max(pool_loans.parent_club_tid, pool_loans.start_date)
            as parent_club_tid,
        max(pool_loans.start_date) as start_date,
        arg_max(pool_loans.end_date, pool_loans.start_date) as end_date,
        arg_max(pool_loans.wage_pct, pool_loans.start_date) as wage_pct,
        arg_max(pool_loans.has_option, pool_loans.start_date) as has_option,
        arg_max(
            case
                when next_snapshots.next_date < pool_loans.end_date
                    then next_snapshots.next_date
            end,
            pool_loans.start_date
        ) as ended_early_by_date
    from pool_loans
    cross join
        unnest(
            range(pool_loans.first_season, pool_loans.last_season + 1)
        ) as seasons (season)
    left join next_snapshots
        on pool_loans.last_pooled_date = next_snapshots.snapshot_date
    group by all
),

-- each player's club on each snapshot, with the date he joined it
held as (
    select
        player.person_id,
        snapshots.season,
        snapshots.snapshot_date,
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

-- the club whose books he was on since before a loan line's season
joined_owners as (
    select
        line_loans.person_id,
        line_loans.season,
        line_loans.borrowing_club_tid,
        arg_min(held.club_tid, held.snapshot_date) as owner_club_tid
    from line_loans
    cross join career
    inner join held
        on
            line_loans.person_id = held.person_id
            and line_loans.season <= held.season
            and held.joined_date < {{ season_start('line_loans.season') }}
            and line_loans.borrowing_club_tid <> held.club_tid
    group by all
),

listed as (
    select
        squads.person_id,
        snapshots.season,
        squads.club_tid as borrowing_club_tid,
        arg_max_null(squads.team_tid, squads.snapshot_date)
            as borrowing_team_tid,
        arg_max_null(squads.record_club_tid, squads.snapshot_date)
            as parent_club_tid,
        min(squads.snapshot_date) as first_seen_date,
        max(squads.snapshot_date) as last_seen_date
    from {{ ref('int_squad_membership') }} as squads
    inner join {{ ref('stg_snapshots') }} as snapshots
        on squads.snapshot_date = snapshots.snapshot_date
    where
        squads.is_loan_in
        and squads.record_club_tid is not null
        and squads.team_type in (
            {% for team_type in var('loan_team_types') %}
            '{{ team_type }}'{% if not loop.last %},{% endif %}
            {% endfor %}
        )
    group by squads.person_id, snapshots.season, squads.club_tid
),

-- each run of our players' weeks on loan, cut into the seasons it touches
slices as (
    select
        spells.person_id,
        spells.start_date,
        spells.end_date,
        {{ season_of('spells.start_date') }} as first_season,
        {{ season_of('spells.end_date') }} as last_season,
        unnest(
            range(
                {{ season_of('spells.start_date') }},
                {{ season_of('spells.end_date') }} + 1
            )
        ) as season
    from {{ ref('int_progress_spells') }} as spells
    cross join career
    where spells.spell_type = 'on_loan'
),

-- the seasons a run of our players' weeks on loan touches
loaned_out as (
    select distinct
        person_id,
        season
    from slices
),

loans as (
    select
        coalesce(pooled.person_id, listed.person_id, line_loans.person_id)
            as person_id,
        coalesce(pooled.season, listed.season, line_loans.season) as season,
        coalesce(
            pooled.borrowing_club_tid,
            listed.borrowing_club_tid,
            line_loans.borrowing_club_tid
        ) as borrowing_club_tid,
        coalesce(
            listed.borrowing_team_tid,
            pooled.borrowing_team_tid,
            line_loans.borrowing_team_tid
        ) as borrowing_team_tid,
        coalesce(
            pooled.parent_club_tid,
            listed.parent_club_tid,
            case
                when loaned_out.person_id is not null
                    then career.managed_club_tid
            end,
            joined_owners.owner_club_tid,
            line_loans.parent_club_tid
        ) as parent_club_tid,
        pooled.start_date as pool_start_date,
        pooled.end_date as pool_end_date,
        pooled.wage_pct,
        pooled.has_option,
        pooled.ended_early_by_date,
        listed.first_seen_date,
        listed.last_seen_date,
        line_loans.person_id is not null as has_line
    from pooled
    full outer join listed
        on
            pooled.person_id = listed.person_id
            and pooled.season = listed.season
            and pooled.borrowing_club_tid = listed.borrowing_club_tid
    full outer join line_loans
        on
            coalesce(pooled.person_id, listed.person_id)
            = line_loans.person_id
            and coalesce(pooled.season, listed.season) = line_loans.season
            and coalesce(pooled.borrowing_club_tid, listed.borrowing_club_tid)
            = line_loans.borrowing_club_tid
    left join joined_owners
        on
            line_loans.person_id = joined_owners.person_id
            and line_loans.season = joined_owners.season
            and line_loans.borrowing_club_tid
            = joined_owners.borrowing_club_tid
    left join loaned_out
        on
            line_loans.person_id = loaned_out.person_id
            and line_loans.season = loaned_out.season
    cross join career
),

ours as (
    select
        loans.person_id,
        loans.season,
        count(*) as loans
    from loans
    cross join career
    where loans.parent_club_tid = career.managed_club_tid
    group by loans.person_id, loans.season
),

-- each slice goes to the latest loan of ours in its season or before, back
-- to the season the run starts in
assigned as (
    select
        slices.person_id,
        slices.season,
        max(ours.season) as loan_season,
        any_value(
            case
                when slices.season = slices.first_season
                    then slices.start_date
                else {{ season_start('slices.season') }}
            end
        ) as start_date,
        any_value(
            case
                when slices.season = slices.last_season
                    then slices.end_date
                else {{ season_end('slices.season') }}
            end
        ) as end_date
    from slices
    cross join career
    inner join ours
        on
            slices.person_id = ours.person_id
            and ours.season between slices.first_season and slices.season
    group by slices.person_id, slices.start_date, slices.season
),

dated as (
    select
        person_id,
        loan_season as season,
        min(start_date) as start_date,
        max(end_date) as end_date
    from assigned
    group by person_id, loan_season
)

select
    loans.person_id,
    loans.season,
    loans.borrowing_club_tid,
    loans.borrowing_team_tid,
    loans.parent_club_tid,
    coalesce(
        loans.pool_start_date,
        case
            when
                loans.parent_club_tid = career.managed_club_tid
                and ours.loans = 1
                then dated.start_date
        end
    ) as start_date,
    coalesce(
        loans.pool_end_date,
        case
            when
                loans.parent_club_tid = career.managed_club_tid
                and ours.loans = 1
                then dated.end_date
        end
    ) as end_date,
    loans.pool_start_date is not null as is_dated_by_pool,
    loans.ended_early_by_date,
    loans.wage_pct,
    loans.has_option,
    loans.first_seen_date,
    loans.last_seen_date,
    loans.has_line
from loans
cross join career
left join dated
    on
        loans.person_id = dated.person_id
        and loans.season = dated.season
left join ours
    on
        loans.person_id = ours.person_id
        and loans.season = ours.season
