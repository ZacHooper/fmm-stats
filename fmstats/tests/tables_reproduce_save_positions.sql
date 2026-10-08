-- The league tables rebuilt from the fixture list reproduce the game's own
-- final positions (fact_competition_outcome.final_position) for every Danish
-- league season, and for the managed club in every league season it
-- finished. A Danish league splits after its preliminary phase into an upper
-- and a lower group that carry their points over: a team's finish is its
-- place on its whole-season points, goal difference and goals scored within
-- the last league stage it played, below every team whose last stage comes
-- earlier. A single-stage league is the same rule with one stage. One row per
-- disagreeing team, plus one if nothing was compared. Assumes every season
-- was seen whole (a full rebuild); other nations' tie-breakers are not read
-- (docs/TODO.md #13), so only Denmark is held league-wide.
with career as (
    select managed_club_tid from {{ ref('stg_career') }}
),

danish as (
    select competitions.cid
    from {{ ref('dim_competition') }} as competitions
    inner join {{ ref('dim_nation') }} as nations
        on competitions.nation_id = nations.nation_id
    where nations.name = 'Denmark'
),

finishes as (
    select
        outcomes.cid,
        outcomes.competition_season,
        outcomes.team_tid,
        outcomes.final_position,
        outcomes.team_tid = career.managed_club_tid as is_managed,
        outcomes.cid in (select danish.cid from danish) as is_danish
    from {{ ref('fact_competition_outcome') }} as outcomes
    cross join career
    where outcomes.final_position is not null
),

stage_tables as (
    select
        standings.cid,
        standings.competition_season,
        standings.stage_index,
        standings.team_tid,
        standings.points,
        standings.goals_for,
        standings.goals_against
    from {{ ref('mart_standings') }} as standings
    where
        standings.is_latest
        and exists (
            select 1 as found
            from finishes
            where
                standings.cid = finishes.cid
                and standings.competition_season = finishes.competition_season
                and (finishes.is_danish or finishes.is_managed)
        )
),

seasons as (
    select
        cid,
        competition_season,
        team_tid,
        max(stage_index) as last_stage,
        sum(points) as points,
        sum(goals_for) - sum(goals_against) as goal_difference,
        sum(goals_for) as goals_for
    from stage_tables
    group by cid, competition_season, team_tid
),

rebuilt as (
    select
        seasons.cid,
        seasons.competition_season,
        seasons.team_tid,
        (
            select count(*) as teams_above
            from seasons as above
            where
                seasons.cid = above.cid
                and seasons.competition_season = above.competition_season
                and above.last_stage < seasons.last_stage
        )
        + row_number() over (
            partition by
                seasons.cid,
                seasons.competition_season,
                seasons.last_stage
            order by
                seasons.points desc,
                seasons.goal_difference desc,
                seasons.goals_for desc,
                seasons.team_tid asc
        ) as rebuilt_position
    from seasons
),

compared as (
    select
        finishes.cid,
        finishes.competition_season,
        finishes.team_tid,
        finishes.is_managed,
        finishes.final_position,
        rebuilt.rebuilt_position
    from finishes
    left join rebuilt
        on
            finishes.cid = rebuilt.cid
            and finishes.competition_season = rebuilt.competition_season
            and finishes.team_tid = rebuilt.team_tid
    where finishes.is_danish or finishes.is_managed
)

select
    case
        when compared.is_managed then 'our finish differs from the save'
        else 'Danish finish differs from the save'
    end as check_name,
    compared.cid,
    compared.competition_season,
    compared.team_tid,
    compared.final_position,
    compared.rebuilt_position
from compared
where compared.rebuilt_position is distinct from compared.final_position
union all
select
    'nothing compared' as check_name,
    null as cid,
    null as competition_season,
    null as team_tid,
    null as final_position,
    null as rebuilt_position
where not exists (
    select 1 as found
    from compared
    where compared.is_managed
)
