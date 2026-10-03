-- Every match in the world once (int_world_matches), placed in its
-- competition, stage and round where the stage is labelled
-- (int_stage_competitions; competition_source says how). Our own match names
-- its competition even outside a stage (a friendly). A knockout match
-- belongs to a tie, the pairing in its round (tie_id); in a two-legged round
-- leg numbers the matches by date. has_detail marks our own matches, which
-- carry events and player stats. score_display is for reading only.
{%- set knockout = var('stage_formats')[0] %}

with placed as (
    select
        matches.*,
        coalesce(stages_of.cid, ours.cid) as cid,
        case
            when stages_of.cid is not null then stages_of.competition_source
            when ours.cid is not null then 'our_match'
        end as competition_source,
        stage_rows.stage_format,
        rounds.legs,
        ours.anchor is not null as has_detail,
        ours.attendance
    from {{ ref('int_world_matches') }} as matches
    left join {{ ref('int_stage_competitions') }} as stages_of
        on
            matches.stage_key = stages_of.stage_key
            and matches.competition_season = stages_of.competition_season
    left join {{ ref('int_stages') }} as stage_rows
        on
            stages_of.cid = stage_rows.cid
            and matches.competition_season = stage_rows.competition_season
            and matches.stage_index = stage_rows.stage_index
    left join {{ ref('int_rounds') }} as rounds
        on
            stages_of.cid = rounds.cid
            and matches.competition_season = rounds.competition_season
            and matches.stage_index = rounds.stage_index
            and matches.round_index = rounds.round_index
    left join {{ ref('int_our_matches') }} as ours
        on matches.match_id = ours.match_id
),

tied as (
    select
        *,
        case
            when stage_format = '{{ knockout }}' and round_index is not null
                then concat_ws(
                    '-', cid, competition_season, stage_index, round_index,
                    least(home_team_tid, away_team_tid),
                    greatest(home_team_tid, away_team_tid)
                )
        end as tie_id
    from placed
)

select
    match_id,
    match_date,
    home_team_tid,
    away_team_tid,
    competition_season,
    cid,
    competition_source,
    stage_index,
    round_index,
    matchday,
    tie_id,
    case
        when legs = 2 and tie_id is not null
            then row_number() over (partition by tie_id order by match_date)
    end as leg,
    home_goals_90,
    away_goals_90,
    home_goals,
    away_goals,
    home_pens,
    away_pens,
    decided_by,
    case
        when home_goals is not null
            then
                home_goals || '-' || away_goals
                || case decided_by
                    when 'ET' then ' aet'
                    when 'pens'
                        then ' (' || home_pens || '-' || away_pens || ' pens)'
                    else ''
                end
    end as score_display,
    has_detail,
    attendance,
    stage_key,
    source_snapshot_date
from tied
