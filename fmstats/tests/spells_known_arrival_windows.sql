{{ config(tags=['known_answers']) }}
-- Frem's arrivals and the window each came in: summer is the first half of
-- the season, winter the second (from 1 January). An arrival is bounded by
-- its dates: a transfer's move_date, else its snapshot gap (moved_after,
-- moved_by]; a loan to us by the snapshot before the first one listing him
-- and that first one. A row for each arrival missing or whose bounds do not
-- put it in the known window.
with career as (
    select * from {{ ref('stg_career') }}
),

snapshots as (
    select
        snapshot_date,
        lag(snapshot_date) over (order by snapshot_date) as previous_date
    from {{ ref('stg_snapshots') }}
),

expected (name, season, arrival_window) as (
    values
    ('Marc Nielsen', 2023, 'winter'),
    ('Anosike Ementa', 2024, 'winter'),
    ('Lauge Sandgrav', 2024, 'winter'),
    ('Anton Pedersen', 2024, 'summer'),
    ('Frederik Ellegaard', 2024, 'summer'),
    ('Rasmus Møller', 2024, 'summer'),
    ('Adam Jakobsen', 2024, 'summer')
),

arrivals as (
    select
        transfers.person_id,
        transfers.season,
        coalesce(transfers.move_date, transfers.moved_after) as earliest,
        coalesce(transfers.move_date, transfers.moved_by) as latest
    from {{ ref('fact_transfer') }} as transfers
    inner join career
        on transfers.to_club_tid = career.managed_club_tid
    union all
    select
        loans.person_id,
        loans.season,
        snapshots.previous_date as earliest,
        loans.first_seen_date as latest
    from {{ ref('fact_loan_spell') }} as loans
    inner join career
        on loans.borrowing_club_tid = career.managed_club_tid
    inner join snapshots
        on loans.first_seen_date = snapshots.snapshot_date
),

windows as (
    select
        people.name,
        arrivals.season,
        case
            when arrivals.earliest >= make_date(arrivals.season, 1, 1)
                then 'winter'
            when arrivals.latest < make_date(arrivals.season, 1, 1)
                then 'summer'
        end as arrival_window
    from arrivals
    inner join {{ ref('dim_person') }} as people
        on arrivals.person_id = people.person_id
)

select
    expected.name,
    expected.season,
    expected.arrival_window as expected_window,
    windows.arrival_window as actual_window
from expected
cross join career
left join windows
    on
        expected.name = windows.name
        and expected.season = windows.season
where
    career.career_key = 'frem'
    and windows.arrival_window is distinct from expected.arrival_window
