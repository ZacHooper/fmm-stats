-- Each round of a knockout stage, from its rules: name, team count and legs. A
-- two-legged tie is one round played twice, home and away swapped (int_matches
-- numbers the legs). League and group stages have no rounds. A rules member
-- can list a round twice with different team counts (competition 95's first
-- round as 12 teams and as 8, in the same snapshot); round_teams is NULL where
-- its versions disagree, and the name and legs, on which they agree, are kept.
select
    seasons.cid,
    seasons.competition_season,
    rounds.stage_index,
    rounds.round_index,
    any_value(round_names.name) as name,
    case
        when count(distinct rounds.round_teams) = 1
            then any_value(rounds.round_teams)
    end as round_teams,
    any_value(rounds.legs) as legs
from {{ ref('int_competition_seasons') }} as seasons
inner join {{ ref('stg_competition_rounds') }} as rounds
    on
        seasons.competition_uid = rounds.competition_uid
        and seasons.rules_snapshot_date = rounds.snapshot_date
left join {{ ref('stg_round_names') }} as round_names
    on
        rounds.snapshot_date = round_names.snapshot_date
        and rounds.round_name_id = round_names.round_name_id
where rounds.round_index is not null
group by
    seasons.cid,
    seasons.competition_season,
    rounds.stage_index,
    rounds.round_index
