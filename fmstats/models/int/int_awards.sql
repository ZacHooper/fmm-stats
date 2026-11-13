-- Every award the game hands out, one row each, as its latest snapshot has it,
-- with what kind it is and how often it is decided.
-- award_type: 'team' for a team of the period (an award with a stored team, or
-- one named Team, XI, Eleven or Squad: 'Team of the Week', 'Dream Team',
-- 'Best XI'), 'manager' for a Manager or Coach award, else 'player' (Player of
-- the Year, Top Goalscorer, Golden Glove ...). period: 'week' for an award of
-- the week or of the round, 'month' for one of the month, else 'season'. Both
-- are read from the award's name; the awards table holds bytes that look like
-- the same two things, not yet named (docs/parser/awards.md).
with awards as (
    {{ latest(ref('stg_awards'), 'award_id') }}
),

team_awards as (
    select distinct award_id
    from {{ ref('stg_award_team_places') }}
)

select
    awards.award_id,
    awards.name,
    awards.short_name,
    case
        when
            team_awards.award_id is not null
            or regexp_matches(
                awards.short_name, '(?i)team|\bxi\b|eleven|squad'
            )
            then 'team'
        when regexp_matches(awards.short_name, '(?i)manager|coach')
            then 'manager'
        else 'player'
    end as award_type,
    case
        when regexp_matches(awards.short_name, '(?i)of the (week|round)')
            then 'week'
        when regexp_matches(awards.short_name, '(?i)of the month')
            then 'month'
        else 'season'
    end as period,
    awards.cid,
    awards.nation_id,
    awards.continent_id,
    awards.last_date,
    awards.last_seen_date
from awards
left join team_awards
    on awards.award_id = team_awards.award_id
