-- Each player's honours, one row per award place or team-of-the-period pick,
-- keyed (person_id, award_id, edition_date): the award, the period it is for
-- (period_label: 'September 2026' for a monthly award, the edition's date for
-- a weekly one, the year an annual award's screen shows), his place (1st to
-- 3rd; NULL on a team pick), his club then, and the score or rating. Manager
-- awards are left out: they go to staff, not players.
with honours as (
    select
        person_id,
        award_id,
        edition_date,
        season,
        place,
        club_tid,
        score,
        null as selection_rating
    from {{ ref('fact_award_place') }}
    union all
    select
        person_id,
        award_id,
        edition_date,
        season,
        null as place,
        club_tid,
        null as score,
        selection_rating
    from {{ ref('fact_award_team_place') }}
)

select
    honours.person_id,
    honours.award_id,
    awards.name as award_name,
    awards.short_name,
    awards.award_type,
    awards.award_period,
    honours.season,
    honours.edition_date,
    case awards.award_period
        when 'month'
            then strftime(honours.edition_date - interval 1 day, '%B %Y')
        when 'week' then strftime(honours.edition_date, '%-d %b %Y')
        else cast(honours.season as varchar)
    end as period_label,
    honours.place,
    honours.club_tid,
    clubs.name as club,
    honours.score,
    round(honours.selection_rating, 2) as selection_rating
from honours
inner join {{ ref('dim_award') }} as awards
    on honours.award_id = awards.award_id
left join {{ ref('dim_club') }} as clubs
    on honours.club_tid = clubs.club_tid
where honours.person_id is not null and awards.award_type != 'manager'
