-- rating_adj covers exactly the starts it can restate: every decoded
-- position maps to a rating role (var('rating_roles')), rating_adj is set for
-- every start with a role and for nothing else, the adjustment adds no player
-- lines, and the raw rating is the one the match record holds. One row per
-- offending player line and check, plus one if the row counts differ.
with player_lines as (
    select
        facts.match_id,
        facts.player_tid,
        facts.position,
        facts.role,
        facts.started,
        facts.rating,
        facts.rating_adj,
        matches.rating as recorded_rating
    from {{ ref('fact_player_match') }} as facts
    inner join {{ ref('int_player_matches') }} as matches
        on
            facts.match_id = matches.match_id
            and facts.player_tid = matches.player_tid
)

select
    'position maps to no rating role' as check_name,
    player_lines.match_id,
    player_lines.player_tid,
    player_lines.position,
    player_lines.started
from player_lines
where player_lines.position is not null and player_lines.role is null
union all
select
    'rating_adj set exactly for starts with a role' as check_name,
    player_lines.match_id,
    player_lines.player_tid,
    player_lines.position,
    player_lines.started
from player_lines
where
    (player_lines.rating_adj is null)
    <> (not player_lines.started or player_lines.role is null)
union all
select
    'raw rating differs from the match record' as check_name,
    player_lines.match_id,
    player_lines.player_tid,
    player_lines.position,
    player_lines.started
from player_lines
where player_lines.rating is distinct from player_lines.recorded_rating
union all
select
    'row counts differ' as check_name,
    null as match_id,
    null as player_tid,
    null as position,
    null as started
where
    (select count(*) as n from {{ ref('int_player_match_ratings') }})
    <> (select count(*) as n from {{ ref('int_player_matches') }})
    or (select count(*) as n from {{ ref('fact_player_match') }})
    <> (select count(*) as n from {{ ref('int_player_matches') }})
