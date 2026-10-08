-- Each appearance for the managed (senior) team in a match with detail, keyed
-- (match_id, person_id): the line the web app aggregates into records, awards
-- and per-player totals, so those count the senior team's matches only, the
-- same matches as site_matches. rating_adj is the rating restated for the
-- position played (int.player_match_ratings). is_player_of_match_award is the
-- game's Player of the Match counted as its club records count it: in
-- competitive matches only. An appearance by the anonymous
-- fillers the save plays reserve games with (no person) is not one.
select
    matches.match_id,
    {{ season_of('match_dims.match_date') }} as season,
    matches.person_id,
    matches.player_tid as tid,
    matches.team_tid,
    matches.opponent_tid,
    match_dims.match_date,
    ours.competition,
    matches.rating,
    matches.rating_adj,
    matches.goals,
    matches.assists,
    matches.minutes,
    matches.started,
    matches.is_player_of_match
    and coalesce(competitions.type <> 'friendly', true)
    as is_player_of_match_award,
    matches.position,
    matches.passes,
    matches.passes_completed,
    matches.key_passes,
    matches.tackles,
    matches.tackles_won,
    matches.interceptions,
    matches.headers,
    matches.headers_won,
    matches.crosses,
    matches.crosses_completed,
    matches.dribbles,
    matches.shots,
    matches.shots_on_target,
    matches.mistakes,
    matches.yellows
from {{ ref('fact_player_match') }} as matches
inner join {{ ref('site_our_teams') }} as teams
    on
        matches.team_tid = teams.team_tid
        and teams.is_managed
inner join {{ ref('dim_match') }} as match_dims
    on matches.match_id = match_dims.match_id
inner join {{ ref('int_our_matches') }} as ours
    on matches.match_id = ours.match_id
left join {{ ref('dim_competition') }} as competitions
    on match_dims.cid = competitions.cid
cross join {{ ref('stg_career') }} as career
where matches.appeared and matches.person_id is not null
