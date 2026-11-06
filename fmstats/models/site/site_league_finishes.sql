-- Where the managed team finished each league season it played: one row per
-- season (by the career's rollover day, from its last match there) and league.
-- final_position is the game's own, from the club league history, once the
-- season is finished; until then it is NULL and table_position is its place in
-- the table of the stage it has reached, stage_name that stage and stage_teams
-- its size. n_teams counts the teams with a match in the competition season.
with career as (
    select * from {{ ref('stg_career') }}
),

sizes as (
    select
        cid,
        competition_season,
        count(*) as n_teams
    from {{ ref('fact_participation') }}
    group by cid, competition_season
)

select
    {{ season_of('entries.last_match_date') }} as season,
    competitions.name as competition,
    outcomes.final_position,
    outcomes.table_position,
    stage_rows.name as stage_name,
    stage_rows.stage_teams,
    sizes.n_teams
from {{ ref('fact_participation') }} as entries
cross join career
inner join {{ ref('dim_competition') }} as competitions
    on entries.cid = competitions.cid
inner join {{ ref('fact_competition_outcome') }} as outcomes
    on
        entries.team_tid = outcomes.team_tid
        and entries.cid = outcomes.cid
        and entries.competition_season = outcomes.competition_season
left join {{ ref('dim_stage') }} as stage_rows
    on
        outcomes.cid = stage_rows.cid
        and outcomes.competition_season = stage_rows.competition_season
        and outcomes.stage_reached = stage_rows.stage_index
inner join sizes
    on
        entries.cid = sizes.cid
        and entries.competition_season = sizes.competition_season
where
    entries.team_tid = career.managed_club_tid
    and competitions.type = 'league'
