-- Each team in each competition season it has a match in, scheduled or
-- played, where the match's stage is labelled (int_matches.cid): its first and
-- last match dates, the matches it has played, and how far it went:
-- stage_reached, and round_reached within that stage when it is a knockout.
-- An unlabelled stage (int_stage_competitions) counts for nothing, so a cup
-- abroad, and a round of our own cups without one of our matches, hold no
-- participation.
with entries as (
    select
        sides.team_tid,
        matches.cid,
        matches.competition_season,
        matches.stage_index,
        matches.round_index,
        matches.match_date,
        matches.home_goals,
        max(matches.stage_index) over (
            partition by sides.team_tid, matches.cid, matches.competition_season
        ) as last_stage_index
    from {{ ref('int_matches') }} as matches
    inner join {{ ref('int_team_matches') }} as sides
        on
            matches.match_date = sides.match_date
            and matches.home_team_tid = sides.home_team_tid
            and matches.away_team_tid = sides.away_team_tid
    where matches.cid is not null and matches.competition_season is not null
)

select
    team_tid,
    cid,
    competition_season,
    min(match_date) as first_match_date,
    max(match_date) as last_match_date,
    count(home_goals) as matches_played,
    max(stage_index) as stage_reached,
    max(round_index) filter (
        where stage_index = last_stage_index
    ) as round_reached
from entries
group by team_tid, cid, competition_season
