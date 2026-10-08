-- rating_adj covers exactly the starts it can restate: every decoded
-- position maps to a rating role (var('rating_roles')), rating_adj is set for
-- every start with a role and for nothing else, the adjustment adds no player
-- lines, and the raw rating is the one the match record holds. One row per
-- offending player line, plus one if the row counts differ.
with lines as (
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
    case
        when lines.position is not null and lines.role is null
            then 'position maps to no rating role'
        when lines.rating is distinct from lines.recorded_rating
            then 'raw rating differs from the match record'
        else 'rating_adj set for a line it should not be, or missing'
    end as check_name,
    lines.match_id,
    lines.player_tid,
    lines.position,
    lines.started
from lines
where
    (lines.position is not null and lines.role is null)
    or lines.rating is distinct from lines.recorded_rating
    or (lines.rating_adj is null) <> (not lines.started or lines.role is null)
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
