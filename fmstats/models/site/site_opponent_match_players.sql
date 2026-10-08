-- Each appearance AGAINST the managed (senior) team in a match with detail,
-- keyed (match_id, person_id): the opposition's line, with the same columns as
-- site_match_players, so the web app can show how a club lined up against us
-- and who hurt us. position is a starter's full-time position.
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
        matches.opponent_tid = teams.team_tid
        and teams.is_managed
inner join {{ ref('dim_match') }} as match_dims
    on matches.match_id = match_dims.match_id
inner join {{ ref('int_our_matches') }} as ours
    on matches.match_id = ours.match_id
left join {{ ref('dim_competition') }} as competitions
    on match_dims.cid = competitions.cid
cross join {{ ref('stg_career') }} as career
where matches.appeared and matches.person_id is not null
