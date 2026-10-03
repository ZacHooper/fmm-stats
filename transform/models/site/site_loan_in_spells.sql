-- mart.loan_in_spells on the new layers, its rules unchanged: a player ever a
-- loanee in our squad (a squad_membership loan-in listing by our club) has a
-- spell for each season he appeared for one of our teams, from that season's
-- window start to its end, cut at the last snapshot listing him on loan unless
-- the newest still does. Seasons start on 1 July (var('site_calendar')).
with newest as (
    select max(phase_date) as phase_date
    from {{ ref('site_snapshots') }}
),

flagged as (
    select
        person_id,
        max(snapshot_date) as last_flagged_date
    from {{ ref('squad_membership') }}
    where is_loan_in and is_managed_club
    group by person_id
),

seasons_played as (
    select
        matches.person_id,
        matches.player_tid as tid,
        {{ season_of('fixtures.match_date') }} as season,
        matches.team_tid,
        min(fixtures.match_date) as first_match
    from {{ ref('fact_player_match') }} as matches
    inner join {{ ref('dim_match') }} as fixtures
        on matches.match_id = fixtures.match_id
    cross join {{ site_calendar() }} as career
    where
        matches.appeared
        and matches.team_tid in (
            select o.club_tid from {{ ref('site_our_clubs') }} as o
        )
    group by all
),

r as (
    select
        seasons_played.person_id,
        seasons_played.tid,
        seasons_played.season,
        seasons_played.team_tid as club_tid,
        seasons_played.first_match,
        seasons_played.first_match as from_phase_date,
        cast(null as date) as prev_phase_date,
        flagged.last_flagged_date
    from seasons_played
    inner join flagged
        on seasons_played.person_id = flagged.person_id
),

spells as (
    select
        r.person_id,
        r.tid,
        people.name,
        'loan_in' as spell_type,
        r.club_tid,
        cast(null as varchar) as club,
        r.season,
        case
            when {{ arrival_window('r') }} = 'winter'
                then {{ winter_cut('r.season') }}
            else {{ season_start('r.season') }}
        end as valid_from,
        case
            when r.last_flagged_date >= newest.phase_date
                then {{ season_end('r.season') }}
            else least({{ season_end('r.season') }}, r.last_flagged_date)
        end as valid_to,
        {{ arrival_window('r') }} as arrival_window
    from r
    cross join {{ site_calendar() }} as career
    cross join newest
    left join {{ ref('dim_person') }} as people
        on r.person_id = people.person_id
)

select
    person_id,
    tid,
    name,
    spell_type,
    club_tid,
    club,
    season,
    valid_from,
    valid_to,
    arrival_window
from spells
where valid_to >= valid_from
