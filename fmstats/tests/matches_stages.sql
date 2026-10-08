-- Every match of the managed team in a competition season the save gives
-- rules for (dim_stage) carries the game's fixture label in site.matches: a
-- stage kind and a non-empty stage name, and a leg when its round is
-- two-legged. A knockout tie is one or two legs, and dim_match never holds
-- more matches of a tie than it has legs.
with tie_matches as (
    select
        tie_id,
        count(*) as n_matches
    from {{ ref('dim_match') }}
    where tie_id is not null
    group by tie_id
)

select
    'unlabelled match in a staged competition' as "check",
    ours.match_id as id
from {{ ref('site_matches') }} as ours
inner join {{ ref('dim_match') }} as matches
    on ours.match_id = matches.match_id
left join {{ ref('dim_round') }} as rounds
    on
        matches.cid = rounds.cid
        and matches.competition_season = rounds.competition_season
        and matches.stage_index = rounds.stage_index
        and matches.round_index = rounds.round_index
where
    exists (
        select 1 as is_staged
        from {{ ref('dim_stage') }} as staged
        where
            matches.cid = staged.cid
            and matches.competition_season = staged.competition_season
    )
    and (
        ours.stage_kind is null
        or coalesce(ours.stage, '') = ''
        or (rounds.legs = 2 and ours.leg is null)
    )
union all
select
    'a tie with more matches than legs, or over two legs' as "check",
    tie_rows.tie_id as id
from {{ ref('mart_tie_results') }} as tie_rows
left join tie_matches
    on tie_rows.tie_id = tie_matches.tie_id
where
    tie_rows.legs not in (1, 2)
    or tie_rows.legs_played > tie_rows.legs
    or tie_matches.n_matches > tie_rows.legs
