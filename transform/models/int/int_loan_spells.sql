-- Every loan the store can see, one row per player, season and borrowing
-- club: keyed (person_id, season, borrowing_club_tid). A loan is a spell on top
-- of an unchanged contract, never a transfer. Two sources:
--   * the career history: a loan line (fee code 'loan') is a season at the
--     borrowing club; the parent club is the club of his last line before it
--     that is not a loan;
--   * the squads: a club's first, b or reserve team listing a player whose
--     own record names another club's team (int.squad_membership is_loan_in;
--     a national side is not a loan). The history has no line for a loan made
--     during the season until it ends, so a current loan is often only here.
-- borrowing_team_tid is the team that lists him, else the loan line's team.
-- parent_club_tid is his record's club where a snapshot lists him, else the
-- club before the loan line. first_seen_date / last_seen_date are the
-- snapshots listing him there (NULL for a loan only the history shows).
--
-- start_date and end_date are real only for a loan out of the club we manage:
-- its first and last week flagged on loan in Player Progress
-- (int.progress_spells), clipped to the season, since a loan lasts at most a
-- season and the flag can run unbroken from one loan into its renewal.
-- Elsewhere the save gives no loan dates and they read NULL.
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

loans as (
    select
        coalesce(listed.person_id, line_loans.person_id) as person_id,
        coalesce(listed.season, line_loans.season) as season,
        coalesce(listed.borrowing_club_tid, line_loans.borrowing_club_tid)
            as borrowing_club_tid,
        coalesce(listed.borrowing_team_tid, line_loans.borrowing_team_tid)
            as borrowing_team_tid,
        coalesce(listed.parent_club_tid, line_loans.parent_club_tid)
            as parent_club_tid,
        listed.first_seen_date,
        listed.last_seen_date,
        line_loans.person_id is not null as has_line
    from listed
    full outer join line_loans
        on
            listed.person_id = line_loans.person_id
            and listed.season = line_loans.season
            and listed.borrowing_club_tid = line_loans.borrowing_club_tid
),

-- our players' weeks out on loan, one row per spell and season it touches
weeks_out as (
    select
        touched.person_id,
        touched.season,
        greatest(
            touched.start_date,
            {{ season_start('touched.season', 'rollover') }}
        ) as start_date,
        least(
            touched.end_date,
            {{ season_end('touched.season', 'rollover') }}
        ) as end_date
    from (
        select
            spells.person_id,
            spells.start_date,
            spells.end_date,
            unnest(
                range(
                    {{ season_of('spells.start_date') }},
                    {{ season_of('spells.end_date') }} + 1
                )
            ) as season
        from {{ ref('int_progress_spells') }} as spells
        cross join career
        where spells.spell_type = 'on_loan'
    ) as touched
    cross join career as rollover
),

dated as (
    select
        person_id,
        season,
        min(start_date) as start_date,
        max(end_date) as end_date
    from weeks_out
    group by person_id, season
)

select
    loans.person_id,
    loans.season,
    loans.borrowing_club_tid,
    loans.borrowing_team_tid,
    loans.parent_club_tid,
    case
        when loans.parent_club_tid = career.managed_club_tid
            then dated.start_date
    end as start_date,
    case
        when loans.parent_club_tid = career.managed_club_tid
            then dated.end_date
    end as end_date,
    loans.first_seen_date,
    loans.last_seen_date,
    loans.has_line
from loans
cross join career
left join dated
    on
        loans.person_id = dated.person_id
        and loans.season = dated.season
