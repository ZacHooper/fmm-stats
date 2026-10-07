-- Each competition season the fixture list labels (int_stage_competitions),
-- with the snapshot whose rules it was played under. A competition's rules
-- change between seasons (a round of 16 teams in 4 groups becomes 32 in 8),
-- and a snapshot holds rules only for the competitions loaded in it, so a
-- season's rules are the earliest snapshot that holds both one of its
-- fixtures and its rules; failing that, the latest snapshot with its rules.
with labelled as (
    select distinct
        labels.cid,
        labels.competition_season,
        fixtures.snapshot_date
    from {{ ref('stg_world_fixtures') }} as fixtures
    inner join {{ ref('int_stage_competitions') }} as labels
        on
            fixtures.stage_key = labels.stage_key
            and fixtures.season_year = labels.competition_season
),

competitions as (
    select distinct
        cid,
        uid as competition_uid
    from {{ ref('stg_competitions') }}
),

rules as (
    select distinct
        competition_uid,
        snapshot_date
    from {{ ref('stg_competition_rounds') }}
),

first_with_rules as (
    select
        labelled.cid,
        labelled.competition_season,
        competitions.competition_uid,
        min(rules.snapshot_date) as snapshot_date
    from labelled
    inner join competitions on labelled.cid = competitions.cid
    left join rules
        on
            competitions.competition_uid = rules.competition_uid
            and labelled.snapshot_date = rules.snapshot_date
    group by
        labelled.cid,
        labelled.competition_season,
        competitions.competition_uid
),

latest_rules as (
    select
        competition_uid,
        max(snapshot_date) as snapshot_date
    from rules
    group by competition_uid
)

select
    first_with_rules.cid,
    first_with_rules.competition_season,
    first_with_rules.competition_uid,
    coalesce(first_with_rules.snapshot_date, latest_rules.snapshot_date)
        as rules_snapshot_date
from first_with_rules
left join latest_rules
    on first_with_rules.competition_uid = latest_rules.competition_uid
