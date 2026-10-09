-- Every transfer the site shows (fact_transfer), named and placed, keyed
-- (person_id, to_line_index):
--   season         the campaign he moved FOR — a June signing belongs to the
--                  next season's market
--   in_career      the season falls inside the career (a site.snapshots
--                  season); earlier rows are the pre-career history the save
--                  keeps for players still in it, which only the record
--                  progression reads
--   transfer_window  summer (June-September) or winter by the move date, else
--                  the first snapshot showing him at the new club; undated
--                  where neither is known
--   age            at the move, the window's date standing in where there is
--                  no move date
--   direction      'in' or 'out' for a move to or from our club (club level:
--                  first team and reserves are one club), NULL otherwise
-- from_* is NULL for a free agent's signing. Club nations are the club's own
-- (dim_club.nation_id), as the season review reads them.
with transfers as (
    select * from {{ ref('fact_transfer') }}
),

ours as (
    select distinct club_tid from {{ ref('site_our_teams') }}
),

clubs as (
    select
        clubs.club_tid,
        clubs.name as club,
        nations.name as nation
    from {{ ref('dim_club') }} as clubs
    left join {{ ref('dim_nation') }} as nations
        on clubs.nation_id = nations.nation_id
),

seasons as (
    select distinct season from {{ ref('site_snapshots') }}
),

dated as (
    select
        transfers.*,
        coalesce(transfers.move_date, transfers.moved_by) as when_date
    from transfers
)

select
    dated.person_id,
    dated.to_line_index,
    people.tid,
    people.name,
    dated.season,
    dated.season in (select seasons.season from seasons) as in_career,
    dated.move_date,
    case
        when dated.when_date is null then 'undated'
        when month(dated.when_date) between 6 and 9 then 'summer'
        else 'winter'
    end as transfer_window,
    {{ age_on('people.dob',
        'coalesce(dated.when_date, make_date(cast(dated.season as integer), 6, 30))') }}
        as age,
    dated.transfer_type,
    dated.fee_kind,
    dated.fee_gbp,
    dated.from_club_tid,
    from_clubs.club as from_club,
    from_clubs.nation as from_nation,
    dated.to_club_tid,
    to_clubs.club as to_club,
    to_clubs.nation as to_nation,
    case
        when dated.to_club_tid in (select ours.club_tid from ours) then 'in'
        when dated.from_club_tid in (select ours.club_tid from ours) then 'out'
    end as direction
from dated
inner join {{ ref('dim_person') }} as people
    on dated.person_id = people.person_id
left join clubs as from_clubs
    on dated.from_club_tid = from_clubs.club_tid
left join clubs as to_clubs
    on dated.to_club_tid = to_clubs.club_tid
