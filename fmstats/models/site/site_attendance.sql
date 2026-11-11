-- The managed team's home crowds per season, from its matches with detail
-- (site.matches): games with an attendance, their average and the largest.
select
    season,
    count(*) as n_games,
    cast(round(avg(attendance)) as integer) as average_attendance,
    min(attendance) as min_attendance,
    max(attendance) as max_attendance
from {{ ref('site_matches') }}
where venue = 'H' and attendance > 0
group by season
