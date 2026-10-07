-- Each knockout tie once (int_matches.tie_id): its two teams (team_a the home
-- side of the first leg), the aggregate of the final scores, the last leg's
-- shoot-out and the winner. A tie is decided once all its legs (the round's
-- rules) are played: on aggregate, then by the last leg's shoot-out. There is
-- no away-goals rule: the save's two-legged ties level on aggregate went to
-- extra time whichever side had scored more away. decided_by is the last
-- leg's ('90', 'ET' or 'pens').
with legs as (
    select
        matches.*,
        rounds.legs,
        first_value(matches.home_team_tid) over (
            partition by matches.tie_id order by matches.match_date
        ) as team_a_tid
    from {{ ref('int_matches') }} as matches
    left join {{ ref('int_rounds') }} as rounds
        on
            matches.cid = rounds.cid
            and matches.competition_season = rounds.competition_season
            and matches.stage_index = rounds.stage_index
            and matches.round_index = rounds.round_index
    where matches.tie_id is not null
),

oriented as (
    select
        *,
        case
            when home_team_tid = team_a_tid then away_team_tid
            else home_team_tid
        end as team_b_tid,
        case
            when home_team_tid = team_a_tid then home_goals else away_goals
        end as goals_a,
        case
            when home_team_tid = team_a_tid then away_goals else home_goals
        end as goals_b,
        case
            when home_team_tid = team_a_tid then home_pens else away_pens
        end as pens_a,
        case
            when home_team_tid = team_a_tid then away_pens else home_pens
        end as pens_b
    from legs
),

last_legs as (
    select
        tie_id,
        pens_a,
        pens_b,
        decided_by
    from oriented
    where home_goals is not null
    qualify row_number() over (partition by tie_id order by match_date desc) = 1
),

ties as (
    select
        tie_id,
        any_value(cid) as cid,
        any_value(competition_season) as competition_season,
        any_value(stage_index) as stage_index,
        any_value(round_index) as round_index,
        any_value(legs) as legs,
        any_value(team_a_tid) as team_a_tid,
        any_value(team_b_tid) as team_b_tid,
        count(home_goals) as legs_played,
        sum(goals_a) as goals_a,
        sum(goals_b) as goals_b,
        min(match_date) as first_match_date,
        max(match_date) as last_match_date
    from oriented
    group by tie_id
),

decided as (
    select
        ties.*,
        last_legs.pens_a,
        last_legs.pens_b,
        last_legs.decided_by,
        ties.legs_played = ties.legs as is_decided
    from ties
    left join last_legs on ties.tie_id = last_legs.tie_id
)

select
    tie_id,
    cid,
    competition_season,
    stage_index,
    round_index,
    legs,
    legs_played,
    first_match_date,
    last_match_date,
    team_a_tid,
    team_b_tid,
    goals_a,
    goals_b,
    pens_a,
    pens_b,
    case when is_decided then decided_by end as decided_by,
    is_decided,
    case
        when not is_decided then null
        when goals_a > goals_b then team_a_tid
        when goals_a < goals_b then team_b_tid
        when pens_a > pens_b then team_a_tid
        when pens_a < pens_b then team_b_tid
    end as winner_tid
from decided
