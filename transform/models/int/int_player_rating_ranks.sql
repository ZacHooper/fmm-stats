-- Each rating's percentile and rank among every player rated in that role on
-- that snapshot.
select
    snapshot_date,
    method,
    role,
    tid,
    rating,
    round(
        100 * percent_rank() over (
            partition by snapshot_date, method, role
            order by rating
        ),
        1
    ) as pctile,
    rank() over (
        partition by snapshot_date, method, role
        order by rating desc
    ) as rank_overall
from {{ ref('int_player_ratings') }}
