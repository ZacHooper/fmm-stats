-- Each club's region on each snapshot: the region of its ground's city, and
-- that region's nation. NULL where the club has no ground in the save or its
-- city names no region.
--
-- home_region_id is the region the regional scores group the club under: its
-- own region where that lies in the home nation (int_home_team_tiers), and
-- one row per other nation for a club of that nation playing in the home
-- nation's leagues (Cardiff and Swansea in England: Wales), keyed by the
-- negated nation_id so it can never meet a region id. NULL for every other
-- club.
with home as (
    select distinct nation_id from {{ ref('int_home_team_tiers') }}
)

select
    club.snapshot_date,
    club.club_tid,
    city.region_id,
    region.nation_id as region_nation_id,
    case
        when region.nation_id in (select home.nation_id from home)
            then city.region_id
        when club.league_nation_id in (select home.nation_id from home)
            then -region.nation_id
    end as home_region_id
from {{ ref('int_club_snapshots') }} as club
left join {{ ref('int_stadiums') }} as stadium
    on club.stadium_id = stadium.stadium_id
left join {{ ref('int_cities') }} as city
    on stadium.city_id = city.city_id
left join {{ ref('int_regions') }} as region
    on city.region_id = region.region_id
