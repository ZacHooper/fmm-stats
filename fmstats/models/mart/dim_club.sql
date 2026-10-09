-- Each club: the name and nations of its first team's record, as its latest
-- snapshot gives them, plus its colours and kits and the two colours of its
-- home shirt (int_club_snapshots). A club owns one or more teams (dim_team).
select
    club_tid,
    name,
    nation_id,
    league_nation_id,
    colours,
    kits,
    shirt_colours,
    last_seen_date
from {{ ref('int_club_list') }}

