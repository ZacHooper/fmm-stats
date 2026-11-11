-- rating_adj covers exactly the starts it can restate: every decoded
-- position maps to a rating role (var('rating_roles')), rating_adj is set for
-- every start in a role whose baseline qualifies (at least
-- var('rating_adj_min_starts') competitive starts by the managed team, with
-- some spread) and for nothing else, the adjustment adds no player lines, and
-- the raw rating is the one the match record holds. One row per offending
-- player line and check, plus one if the row counts differ.
with career as (
    select managed_club_tid from {{ ref('stg_career') }}
),

qualified_roles as (
    select facts.rating_role as role
    from {{ ref('fact_player_match') }} as facts
    inner join career
        on facts.team_tid = career.managed_club_tid
    inner join {{ ref('dim_match') }} as matches
        on facts.match_id = matches.match_id
    left join {{ ref('dim_competition') }} as competitions
        on matches.cid = competitions.cid
    where
        facts.is_starter
        and facts.rating_role is not null
        and competitions.type is distinct from 'friendly'
    group by facts.rating_role
    having
        count(*) >= {{ var('rating_adj_min_starts') }}
        and stddev_samp(facts.rating) > 0
),

player_lines as (
    select
        facts.match_id,
        facts.player_tid,
        facts.position,
        facts.rating_role as role,
        facts.is_starter,
        facts.rating,
        facts.rating_adj,
        matches.rating as recorded_rating,
        facts.rating_role in (select qualified_roles.role from qualified_roles)
            as role_qualifies
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
    player_lines.is_starter
from player_lines
where player_lines.position is not null and player_lines.role is null
union all
select
    'rating_adj set exactly for starts in a qualifying role' as check_name,
    player_lines.match_id,
    player_lines.player_tid,
    player_lines.position,
    player_lines.is_starter
from player_lines
where
    (player_lines.rating_adj is null)
    <> (
        not player_lines.is_starter
        or not coalesce(player_lines.role_qualifies, false)
    )
union all
select
    'raw rating differs from the match record' as check_name,
    player_lines.match_id,
    player_lines.player_tid,
    player_lines.position,
    player_lines.is_starter
from player_lines
where player_lines.rating is distinct from player_lines.recorded_rating
union all
select
    'row counts differ' as check_name,
    null as match_id,
    null as player_tid,
    null as position,
    null as is_starter
where
    (select count(*) as n from {{ ref('int_player_match_ratings') }})
    <> (select count(*) as n from {{ ref('int_player_matches') }})
    or (select count(*) as n from {{ ref('fact_player_match') }})
    <> (select count(*) as n from {{ ref('int_player_matches') }})
