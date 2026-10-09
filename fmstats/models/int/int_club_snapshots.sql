-- Each club on each snapshot: what its teams share, read from its first team's
-- record (int_teams). A reserve side stores no stadium and empty kits of its
-- own, so the club's ground, colours and kits are the first team's.
-- nation_id is the club's home nation and league_nation_id the nation whose
-- league it plays in (Cardiff City: Wales, England). affiliates is the club
-- record's list of affiliation links, dates as stored.
--
-- shirt_colours is the home shirt as two colours, main first: the first kit's
-- second slot, then its first or third, whichever differs from the main colour
-- by shirt_colour_min_distance (Frem: navy, red). A plain shirt, with neither,
-- is the main colour twice. A club in the game's stock kit (default_kit) has
-- its name colours instead, background then text.
{%- set min_distance = var('shirt_colour_min_distance') %}
with kits as (
    select
        snapshot_date,
        tid,
        from_json(kits -> '$[0]', '["VARCHAR"]') as home,
        from_json(colours, '["VARCHAR"]') as badge
    from {{ ref('stg_club_details') }}
),

shirts as (
    select
        snapshot_date,
        tid,
        case
            when home = {{ var('default_kit') }}::varchar[]
                then [badge[2], badge[1]]
            else [
                home[2],
                case
                    when
                        {{ colour_distance('home[1]', 'home[2]') }}
                        > {{ min_distance }}
                        then home[1]
                    when
                        {{ colour_distance('home[3]', 'home[2]') }}
                        > {{ min_distance }}
                        then home[3]
                    else home[2]
                end
            ]
        end as shirt_colours
    from kits
),

affiliates as (
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
    details.colours,
    details.kits,
    shirts.shirt_colours,
    coalesce(affiliates.affiliates, []) as affiliates,
    teams.snapshot_date = max(teams.snapshot_date) over () as is_current
from {{ ref('int_teams') }} as teams
inner join {{ ref('stg_club_details') }} as details
    on
        teams.snapshot_date = details.snapshot_date
        and teams.team_tid = details.tid
left join shirts
    on
        teams.snapshot_date = shirts.snapshot_date
        and teams.team_tid = shirts.tid
left join affiliates
    on
        teams.snapshot_date = affiliates.snapshot_date
        and teams.club_tid = affiliates.club_tid
where teams.is_first_team
