-- How many teams each competition has, from the nations' rule files. uid is
-- the competition's (stg_competitions.uid).
select
    cast(phase as date) as snapshot_date,
    uid as competition_uid,
    teams
from {{ source('raw', 'competition_team_counts') }}
