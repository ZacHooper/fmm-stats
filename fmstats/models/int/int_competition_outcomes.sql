-- How each participation (int_participations) ended. final_position is the
-- game's own, from the club league history (a finished league season; the
-- latest snapshot holding it). table_position is the team's place in the
-- table of the stage it reached at its latest matchday (int_standings; the
-- later table where it is in two of that stage's groups), NULL for a knockout
-- stage. is_winner is final_position 1, or, where the
-- competition's final stage is a knockout, winning that stage's last round's
-- tie (int_ties); NULL until the save decides either.
{%- set knockout = var('stage_formats')[0] %}

with league_finishes as (
    select
        club_tid as team_tid,
        league_cid as cid,
        season - 1 as competition_season,
        position
    from {{ ref('stg_club_league_history') }}
    qualify
        snapshot_date = max(snapshot_date) over (
            partition by club_tid, league_cid, season
        )
),

final_rounds as (
    select
        cid,
        competition_season,
        stage_index,
        max(round_index) as round_index
    from {{ ref('int_rounds') }}
    group by all
),

final_ties as (
    select
        tie_rows.cid,
        tie_rows.competition_season,
        tie_rows.winner_tid
    from {{ ref('int_ties') }} as tie_rows
    inner join {{ ref('int_stages') }} as stage_rows
        on
            tie_rows.cid = stage_rows.cid
            and tie_rows.competition_season = stage_rows.competition_season
            and tie_rows.stage_index = stage_rows.stage_index
    inner join final_rounds
        on
            tie_rows.cid = final_rounds.cid
            and tie_rows.competition_season = final_rounds.competition_season
            and tie_rows.stage_index = final_rounds.stage_index
            and tie_rows.round_index = final_rounds.round_index
    where
        stage_rows.is_final_stage
        and stage_rows.stage_format = '{{ knockout }}'
        and tie_rows.winner_tid is not null
),

latest_tables as (
    select
        cid,
        competition_season,
        stage_index,
        team_tid,
        position
    from {{ ref('int_standings') }}
    where is_latest
    qualify
        row_number() over (
            partition by cid, competition_season, stage_index, team_tid
            order by through_date desc
        ) = 1
)

select
    entries.team_tid,
    entries.cid,
    entries.competition_season,
    entries.stage_reached,
    entries.round_reached,
    finishes.position as final_position,
    latest_tables.position as table_position,
    case
        when finishes.position is not null then finishes.position = 1
        when final_ties.winner_tid is not null
            then final_ties.winner_tid = entries.team_tid
    end as is_winner
from {{ ref('int_participations') }} as entries
left join league_finishes as finishes
    on
        entries.team_tid = finishes.team_tid
        and entries.cid = finishes.cid
        and entries.competition_season = finishes.competition_season
left join latest_tables
    on
        entries.team_tid = latest_tables.team_tid
        and entries.cid = latest_tables.cid
        and entries.competition_season = latest_tables.competition_season
        and entries.stage_reached = latest_tables.stage_index
left join final_ties
    on
        entries.cid = final_ties.cid
        and entries.competition_season = final_ties.competition_season
