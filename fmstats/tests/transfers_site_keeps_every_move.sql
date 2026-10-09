-- site.transfers names every move in fact_transfer: the join to dim_person
-- drops none, and a move to or from our club carries a direction.
with site_rows as (
    select count(*) as n from {{ ref('site_transfers') }}
),

mart_rows as (
    select count(*) as n from {{ ref('fact_transfer') }}
),

our_clubs as (
    select teams.club_tid from {{ ref('site_our_teams') }} as teams
),

undirected as (
    select count(*) as n
    from {{ ref('site_transfers') }} as transfers
    where
        transfers.direction is null
        and (
            transfers.to_club_tid in (select our_clubs.club_tid from our_clubs)
            or transfers.from_club_tid in (
                select our_clubs.club_tid from our_clubs
            )
        )
)

select
    'row count' as "check",
    site_rows.n as site_rows,
    mart_rows.n as mart_rows
from site_rows
cross join mart_rows
where site_rows.n <> mart_rows.n
union all
select
    'our move without a direction' as "check",
    undirected.n as site_rows,
    null as mart_rows
from undirected
where undirected.n > 0
