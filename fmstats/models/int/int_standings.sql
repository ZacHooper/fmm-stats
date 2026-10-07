-- Each league or group stage's table after every matchday it has played: one
-- row per team and matchday, with the totals of the team's matches of that
-- matchday and earlier (a postponed match counts on its own matchday once it
-- is played), and its position. through_date is the latest match date the
-- totals include. A group is a stage_key. Positions rank points, goal
-- difference and goals scored; the save's tie-breakers past those are not
-- read, so teams level on all three are ordered by team_tid. A stage holds
-- only its own matches: a split league's championship and relegation groups
-- are stages of their own, and whether the game carries points into them is
-- not read either. A stage's format is its rules'; a stage with none (a
-- reserve group) is a league stage when its competition's type is a league's
-- (var('league_competition_types')) or the league rule labelled it
-- (competition_source 'league_structure', which only labels league stages).
-- Knockout stages have ties instead (int_ties), and a stage with no
-- competition has no format.
{%- set knockout = var('stage_formats')[0] %}
{%- set league = var('stage_formats')[1] %}

with games as (
    select
        matches.cid,
        matches.competition_season,
        matches.stage_index,
        matches.stage_key,
        matches.matchday,
        matches.match_date,
        sides.team_tid,
        sides.goals_for,
        sides.goals_against,
        sides.result,
        sides.points
    from {{ ref('int_matches') }} as matches
    inner join {{ ref('int_competitions') }} as competitions
        on matches.cid = competitions.cid
    left join {{ ref('int_stages') }} as stage_rows
        on
            matches.cid = stage_rows.cid
            and matches.competition_season = stage_rows.competition_season
            and matches.stage_index = stage_rows.stage_index
    inner join {{ ref('int_team_matches') }} as sides
        on
            matches.match_id = sides.match_id
    where
        coalesce(
            stage_rows.stage_format,
            case
                when
                    competitions.type in (
                        {% for type in var('league_competition_types') %}
                        '{{ type }}'{% if not loop.last %},{% endif %}
                        {% endfor %}
                    )
                    or matches.competition_source = 'league_structure'
                    then '{{ league }}'
            end
        ) != '{{ knockout }}'
        and matches.home_goals is not null
        and matches.matchday is not null
),

team_matchdays as (
    select
        cid,
        competition_season,
        stage_index,
        stage_key,
        team_tid,
        matchday,
        count(*) as played,
        count(*) filter (where result = 'W') as won,
        count(*) filter (where result = 'D') as drawn,
        count(*) filter (where result = 'L') as lost,
        sum(goals_for) as goals_for,
        sum(goals_against) as goals_against,
        sum(points) as points
    from games
    group by all
),

matchdays as (
    select
        cid,
        competition_season,
        stage_index,
        stage_key,
        matchday,
        max(max(match_date)) over (
            partition by cid, competition_season, stage_index, stage_key
            order by matchday
        ) as through_date
    from games
    group by cid, competition_season, stage_index, stage_key, matchday
),

teams as (
    select distinct
        cid,
        competition_season,
        stage_index,
        stage_key,
        team_tid
    from games
),

totals as (
    select
        teams.cid,
        teams.competition_season,
        teams.stage_index,
        teams.stage_key,
        matchdays.matchday,
        matchdays.through_date,
        teams.team_tid,
        {% for total in ['played', 'won', 'drawn', 'lost', 'goals_for',
                         'goals_against', 'points'] %}
        cast(coalesce(sum(team_matchdays.{{ total }}) over (
            partition by
                teams.cid,
                teams.competition_season,
                teams.stage_index,
                teams.stage_key,
                teams.team_tid
            order by matchdays.matchday
        ), 0) as integer) as {{ total }}{% if not loop.last %},{% endif %}
        {% endfor %}
    from teams
    inner join matchdays
        on
            teams.cid = matchdays.cid
            and teams.competition_season = matchdays.competition_season
            and teams.stage_index = matchdays.stage_index
            and teams.stage_key = matchdays.stage_key
    left join team_matchdays
        on
            teams.cid = team_matchdays.cid
            and teams.competition_season = team_matchdays.competition_season
            and teams.stage_index = team_matchdays.stage_index
            and teams.stage_key = team_matchdays.stage_key
            and teams.team_tid = team_matchdays.team_tid
            and matchdays.matchday = team_matchdays.matchday
)

select
    cid,
    competition_season,
    stage_index,
    stage_key,
    matchday,
    through_date,
    row_number() over (
        partition by cid, competition_season, stage_index, stage_key, matchday
        order by
            points desc,
            goals_for - goals_against desc,
            goals_for desc,
            team_tid asc
    ) as position,
    team_tid,
    played,
    won,
    drawn,
    lost,
    goals_for,
    goals_against,
    goals_for - goals_against as goal_difference,
    points,
    matchday = max(matchday) over (
        partition by cid, competition_season, stage_index, stage_key
    ) as is_latest
from totals
