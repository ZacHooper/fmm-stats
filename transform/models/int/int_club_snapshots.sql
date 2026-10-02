-- Each club on each snapshot: what its teams share, read from its first team's
-- record (int_teams). A reserve side stores no stadium and empty kits of its
-- own, so the club's ground, colours, kits and academy are the first team's.
-- nation_id is the club's home nation and league_nation_id the nation whose
-- league it plays in (Cardiff City: Wales, England). affiliates is the club
-- record's list of affiliation links, dates as stored.
with affiliates as (
    select
        snapshot_date,
        club_tid,
        list(
            {
                'club1_tid': club1_tid,
                'club2_tid': club2_tid,
                'start_day': start_day,
                'start_year': start_year,
                'end_day': end_day,
                'end_year': end_year
            }
            order by seq
        ) as affiliates
    from {{ ref('stg_club_affiliates') }}
    group by snapshot_date, club_tid
)

select
    teams.snapshot_date,
    teams.club_tid,
    teams.name,
    details.nation_id,
    details.league_nation_id,
    details.stadium_id,
    details.academy,
    details.colours,
    details.kits,
    coalesce(affiliates.affiliates, []) as affiliates,
    teams.snapshot_date = max(teams.snapshot_date) over () as is_current
from {{ ref('int_teams') }} as teams
inner join {{ ref('stg_club_details') }} as details
    on
        teams.snapshot_date = details.snapshot_date
        and teams.team_tid = details.tid
left join affiliates
    on
        teams.snapshot_date = affiliates.snapshot_date
        and teams.club_tid = affiliates.club_tid
where teams.is_first_team
