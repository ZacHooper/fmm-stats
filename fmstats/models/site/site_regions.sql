-- Each region of the home nation (dim_home_region) on each snapshot, for the
-- World page's Regions tab: its clubs' Elo four ways and facilities
-- (fact_region_snapshot), and whether the managed club plays there.
with ours as (
    select
        clubs.snapshot_date,
        clubs.home_region_id
    from {{ ref('fact_club_region_snapshot') }} as clubs
    inner join {{ ref('stg_career') }} as career
        on clubs.team_tid = career.managed_club_tid
)

select
    scores.snapshot_date,
    scores.home_region_id,
    regions.name,
    regions.is_nation_group,
    ours.home_region_id is not null as is_managed_club,
    scores.n_teams,
    scores.elo_mean,
    scores.elo_median,
    scores.elo_top3,
    scores.elo_p75_share,
    scores.youth_facilities_median,
    scores.n_good_youth_facilities,
    scores.training_facilities_median,
    scores.n_good_training_facilities
from {{ ref('fact_region_snapshot') }} as scores
inner join {{ ref('dim_home_region') }} as regions
    on scores.home_region_id = regions.home_region_id
left join ours
    on
        scores.snapshot_date = ours.snapshot_date
        and scores.home_region_id = ours.home_region_id
