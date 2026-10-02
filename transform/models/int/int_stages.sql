-- Each stage of each labelled competition season, from its rules: format
-- (var('stage_formats'): knockout, league or group), team count, groups and
-- name. is_final_stage marks the competition season's last stage, whose
-- outcome decides the winner.
{%- set formats = var('stage_formats') %}

with stages as (
    select
        seasons.cid,
        seasons.competition_season,
        rounds.stage_index,
        any_value(rounds.stage_code) as stage_code,
        any_value(rounds.stage_type) as stage_type,
        any_value(rounds.stage_teams) as stage_teams,
        any_value(rounds.n_groups) as n_groups,
        any_value(rounds.stage_name_id) as stage_name_id,
        any_value(rounds.snapshot_date) as rules_snapshot_date
    from {{ ref('int_competition_seasons') }} as seasons
    inner join {{ ref('stg_competition_rounds') }} as rounds
        on
            seasons.competition_uid = rounds.competition_uid
            and seasons.rules_snapshot_date = rounds.snapshot_date
    group by seasons.cid, seasons.competition_season, rounds.stage_index
)

select
    stages.cid,
    stages.competition_season,
    stages.stage_index,
    stages.stage_code,
    stages.stage_type,
    case stages.stage_type
        {% for code, name in formats.items() %}
        when {{ code }} then '{{ name }}'
        {% endfor %}
    end as stage_format,
    round_names.name,
    stages.stage_teams,
    stages.n_groups,
    stages.stage_index = max(stages.stage_index) over (
        partition by stages.cid, stages.competition_season
    ) as is_final_stage
from stages
left join {{ ref('stg_round_names') }} as round_names
    on
        stages.rules_snapshot_date = round_names.snapshot_date
        and stages.stage_name_id = round_names.round_name_id
