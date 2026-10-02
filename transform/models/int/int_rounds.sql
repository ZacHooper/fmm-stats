-- Each round of a knockout stage, from its rules: name, team count and legs. A
-- two-legged tie is one round played twice, home and away swapped (int_matches
-- numbers the legs). League and group stages have no rounds.
select
    seasons.cid,
    seasons.competition_season,
    rounds.stage_index,
    rounds.round_index,
    round_names.name,
    rounds.round_teams,
    rounds.legs
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
