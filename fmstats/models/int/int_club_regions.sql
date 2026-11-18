-- Each club's region on each snapshot: the region of its ground's city, and
-- that region's nation. NULL where the club has no ground in the save or its
-- city names no region.
select
    club.snapshot_date,
    club.club_tid,
    city.region_id,
    region.nation_id as region_nation_id
from {{ ref('int_club_snapshots') }} as club
left join {{ ref('int_stadiums') }} as stadium
    on club.stadium_id = stadium.stadium_id
left join {{ ref('int_cities') }} as city
    on stadium.city_id = city.city_id
left join {{ ref('int_regions') }} as region
    on city.region_id = region.region_id
