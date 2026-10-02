-- Each club: the name and nations of its first team's record, as its latest
-- snapshot gives them. A club owns one or more teams (dim_team).
select
    club_tid,
    name,
    nation_id,
    league_nation_id,
    last_seen_date
from {{ ref('int_club_list') }}
