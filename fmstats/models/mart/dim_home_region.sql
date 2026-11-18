-- The regions the regional scores group by: each region of the career's home
-- nation, plus one row per other nation whose clubs play in its leagues
-- (Wales, for England's Cardiff, Swansea, Newport, Wrexham and Merthyr),
-- keyed by the negated nation_id. region_ids lists the game's regions a row
-- covers.
with used as (
    select distinct
        home_region_id,
        region_id
    from {{ ref('int_club_regions') }}
    where home_region_id is not null
)

select
    used.home_region_id,
    coalesce(
        any_value(region.name) filter (where used.home_region_id >= 0),
        any_value(nation.name)
    ) as name,
    any_value(region.nation_id) as nation_id,
    used.home_region_id < 0 as is_nation_group,
    list(used.region_id order by used.region_id) as region_ids
from used
inner join {{ ref('int_regions') }} as region
    on used.region_id = region.region_id
inner join {{ ref('int_nations') }} as nation
    on region.nation_id = nation.nation_id
group by used.home_region_id
