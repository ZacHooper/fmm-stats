-- Each region's clubs on each snapshot: the scored tiers' teams of the home
-- nation's men's leagues, grouped by the region of their ground. Elo four
-- ways (mean, median, the best three, and the share of the region's teams at
-- or above the nation's 75th percentile), and facilities (the median, and the
-- teams at var('region_facilities_good_min') or more).
with clubs as (
    select *
    from {{ ref('fact_club_region_snapshot') }}
    where is_scored and home_region_id is not null
),

bar as (
    select
        snapshot_date,
        quantile_cont(elo, 0.75) as elo_p75
    from clubs
    group by snapshot_date
),

ranked as (
    select
        clubs.*,
        bar.elo_p75,
        row_number() over (
            partition by clubs.snapshot_date, clubs.home_region_id
            order by clubs.elo desc
        ) as elo_rank
    from clubs
    inner join bar on clubs.snapshot_date = bar.snapshot_date
)

select
    snapshot_date,
    home_region_id,
    count(*) as n_teams,
    avg(elo) as elo_mean,
    median(elo) as elo_median,
    avg(elo) filter (where elo_rank <= 3) as elo_top3,
    avg(case when elo >= elo_p75 then 1.0 else 0.0 end) as elo_p75_share,
    median(youth_facilities) as youth_facilities_median,
    count(*) filter (
        where youth_facilities >= {{ var('region_facilities_good_min') }}
    ) as n_good_youth_facilities,
    median(training_facilities) as training_facilities_median,
    count(*) filter (
        where training_facilities >= {{ var('region_facilities_good_min') }}
    ) as n_good_training_facilities
from ranked
group by snapshot_date, home_region_id
