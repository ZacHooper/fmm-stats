-- The managed team's matches with detail (int.our_matches), keyed match_id,
-- from its side: season (by the career's rollover day), venue, opponent, the
-- final score, result and points (fact_team_match), formation, attendance,
-- the stage, and each side's team stats (our_ / opp_).
--
-- stage_kind: League or Group for a league or group stage; for a knockout
-- stage, Qualifying where it comes before the competition's group stage in a
-- competition with no league stage, else Knockout; NULL for a match in no
-- stage (a friendly). stage is the game's own label: a league stage's name,
-- 'Group ' and the group's letter (its place among the stage's groups), or
-- the stage and round names. matchday counts from 1 in a league or group,
-- leg is set in a two-legged tie, tie_gf / tie_ga are its aggregate once both
-- legs are played and went_through says whether we won a decided tie.
with career as (
    select * from {{ ref('stg_career') }}
),

stages as (
    select
        *,
        min(case when stage_format = 'group' then stage_index end) over (
            partition by cid, competition_season
        ) as group_stage_index,
        bool_or(stage_format = 'league') over (
            partition by cid, competition_season
        ) as has_league_stage
    from {{ ref('dim_stage') }}
),

-- a group's letter: its place among the stage keys of its stage that the
-- world fixture list starts within var('site_group_draw_days') of it, no
-- further back than the stage has groups (the fixture list names a
-- competition for our own group only)
first_dates as (
    select
        competition_season,
        stage_index,
        stage_key,
        min(match_date) as first_date
    from {{ ref('int_world_matches') }}
    group by competition_season, stage_index, stage_key
),

groups as (
    select
        world.match_id,
        count(*) as group_number
    from {{ ref('int_world_matches') }} as world
    inner join {{ ref('dim_match') }} as matches
        on world.match_id = matches.match_id
    inner join stages
        on
            matches.cid = stages.cid
            and matches.competition_season = stages.competition_season
            and matches.stage_index = stages.stage_index
            and stages.stage_format = 'group'
    inner join first_dates as ours
        on
            world.competition_season = ours.competition_season
            and world.stage_key = ours.stage_key
    inner join first_dates as other_groups
        on
            ours.competition_season = other_groups.competition_season
            and ours.stage_index = other_groups.stage_index
            and ours.stage_key >= other_groups.stage_key
            and other_groups.stage_key
            > ours.stage_key - coalesce(stages.n_groups, 1)
            and abs(date_diff('day', other_groups.first_date, ours.first_date))
            <= {{ var('site_group_draw_days') }}
    group by world.match_id
)

select
    ours.match_id,
    {{ season_of('ours.match_date') }} as season,
    ours.match_date,
    ours.competition,
    sides.venue,
    opponents.name as opponent,
    sides.opponent_tid as opp_tid,
    sides.goals_for as gf,
    sides.goals_against as ga,
    sides.result,
    sides.points as pts,
    sides.formation,
    ours.attendance,
    case stages.stage_format
        when 'league' then 'League'
        when 'group' then 'Group'
        when 'knockout'
            then
                case
                    when
                        not stages.has_league_stage
                        and stages.stage_index < stages.group_stage_index
                        then 'Qualifying'
                    else 'Knockout'
                end
    end as stage_kind,
    case stages.stage_format
        when 'league' then stages.name
        when
            'group'
            then 'Group ' || chr(64 + cast(groups.group_number as integer))
        else concat_ws(' · ', stages.name, rounds.name)
    end as stage,  -- noqa: RF04
    case
        when stages.stage_format in ('league', 'group')
            then matches.matchday + 1
    end as matchday,
    case when rounds.legs = 2 then matches.leg end as leg,
    case
        when tie_rows.legs = 2 and tie_rows.legs_played = 2
            then
                case
                    when
                        tie_rows.team_a_tid = sides.team_tid
                        then tie_rows.goals_a
                    else tie_rows.goals_b
                end
    end as tie_gf,
    case
        when tie_rows.legs = 2 and tie_rows.legs_played = 2
            then
                case
                    when
                        tie_rows.team_a_tid = sides.team_tid
                        then tie_rows.goals_b
                    else tie_rows.goals_a
                end
    end as tie_ga,
    case
        when stages.stage_format = 'knockout' and tie_rows.is_decided
            then tie_rows.winner_tid = sides.team_tid
    end as went_through,
    matches.decided_by in ('ET', 'pens') as extra_time,
    sides.pens_for,
    sides.pens_against,
    {% for stat in var('team_match_stats') %}
    sides.{{ stat }} as our_{{ stat }},
    against.{{ stat }} as opp_{{ stat }}{% if not loop.last %},{% endif %}
    {% endfor %}
from {{ ref('int_our_matches') }} as ours
cross join career
inner join {{ ref('fact_team_match') }} as sides
    on
        ours.match_id = sides.match_id
        and career.managed_club_tid = sides.team_tid
inner join {{ ref('fact_team_match') }} as against
    on
        ours.match_id = against.match_id
        and sides.opponent_tid = against.team_tid
inner join {{ ref('dim_match') }} as matches
    on ours.match_id = matches.match_id
left join {{ ref('dim_team') }} as opponents
    on sides.opponent_tid = opponents.team_tid
left join stages
    on
        matches.cid = stages.cid
        and matches.competition_season = stages.competition_season
        and matches.stage_index = stages.stage_index
left join {{ ref('dim_round') }} as rounds
    on
        matches.cid = rounds.cid
        and matches.competition_season = rounds.competition_season
        and matches.stage_index = rounds.stage_index
        and matches.round_index = rounds.round_index
left join {{ ref('tie_results') }} as tie_rows
    on matches.tie_id = tie_rows.tie_id
left join groups
    on ours.match_id = groups.match_id
