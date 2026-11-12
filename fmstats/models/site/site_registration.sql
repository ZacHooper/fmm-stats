-- Each player in our squad on each snapshot as the registration page reads
-- him, keyed (snapshot_date, person_id), under the career's rule set
-- (stg_career.registration_rule_set, stg_registration_rules; a house rule:
-- docs/danish-registration-rules.md, docs/english-registration-rules.md):
--   b_list          free of the list cap by age: born on or after the rule
--                   set's free_born_from day of the season's first calendar
--                   year less free_under_age (false with no rule set)
--   hg_club         trained at the club: he came out of it (an academy
--                   product, or his origin club is ours), or he has
--                   var('home_grown_months') months with us in his window
--                   (int.squad_training); hg_basis says which (academy /
--                   youth-origin / clock)
--   hg_association  trained in a home-grown nation (the rule set's
--                   hg_nations, else the managed club's own): hg_club, or his
--                   origin club is of one, or he has the months at another
--                   club of one
--   months_club, months_to_go, hg_eta   his months with us, how many he
--                   lacks, and the day he reaches them if he stays, where that
--                   lies inside his window
--   window_open     his window has not closed
--   origin_club, origin_nation, via_academy   where he came from
{% set months = var('home_grown_months') %}
with career as (
    select * from {{ ref('stg_career') }}
),

-- The rule set's free-list age and cut-off and its home-grown nations, the
-- same on each of its rows (registration_rule_sets tests it).
rule_set as (
    select
        any_value(rules.free_under_age) as free_under_age,
        any_value(rules.free_born_from) as free_born_from,
        any_value(rules.hg_nations) as hg_nations
    from {{ ref('stg_registration_rules') }} as rules
    inner join career on rules.rule_set = career.registration_rule_set
),

hg_nations as (
    select nations.nation_id from {{ ref('dim_nation') }} as nations
    where
        list_contains(
            string_split((select rule_set.hg_nations from rule_set), '|'),
            nations.name
        )
    union all
    select clubs.nation_id from {{ ref('dim_club') }} as clubs
    inner join career on clubs.club_tid = career.managed_club_tid
    where (select rule_set.hg_nations from rule_set) is null
),

training as (
    select
        training.snapshot_date,
        training.person_id,
        max(training.months) filter (
            where training.club_tid = career.managed_club_tid
        ) as months_club,
        max(training.months) filter (
            where
            training.club_tid <> career.managed_club_tid
            and clubs.nation_id in (select hg_nations.nation_id from hg_nations)
        ) as months_domestic
    from {{ ref('int_squad_training') }} as training
    cross join career
    left join {{ ref('dim_club') }} as clubs
        on training.club_tid = clubs.club_tid
    group by training.snapshot_date, training.person_id
),

players as (
    select
        squad.snapshot_date,
        squad.person_id,
        snapshots.season,
        people.dob,
        snapshot_players.age,
        people.origin_club_tid,
        people.origin_youth_team_tid is not null as via_academy,
        origins.name as origin_club,
        origin_nations.name as origin_nation,
        origins.nation_id in (select hg_nations.nation_id from hg_nations)
            as origin_is_domestic,
        people.origin_club_tid = career.managed_club_tid as origin_is_ours,
        coalesce(training.months_club, 0) as months_club,
        coalesce(training.months_domestic, 0) as months_domestic,
        {{ season_end(
            season_of('people.dob + interval ' ~ var('home_grown_window_ages')[1]
                ~ ' year')
        ) }} as window_to
    from {{ ref('int_our_squad') }} as squad
    cross join career
    inner join {{ ref('stg_snapshots') }} as snapshots
        on squad.snapshot_date = snapshots.snapshot_date
    inner join {{ ref('dim_person') }} as people
        on squad.person_id = people.person_id
    left join {{ ref('fact_player_snapshot') }} as snapshot_players
        on
            squad.snapshot_date = snapshot_players.snapshot_date
            and squad.person_id = snapshot_players.person_id
    left join {{ ref('dim_club') }} as origins
        on people.origin_club_tid = origins.club_tid
    left join {{ ref('dim_nation') }} as origin_nations
        on origins.nation_id = origin_nations.nation_id
    left join training
        on
            squad.snapshot_date = training.snapshot_date
            and squad.person_id = training.person_id
)

select
    snapshot_date,
    person_id,
    dob,
    age,
    coalesce(dob >= make_date(
        cast(season as integer)
        - 1
        - (select rule_set.free_under_age from rule_set),
        cast(split_part(
            (select rule_set.free_born_from from rule_set), '-', 1
        ) as integer),
        cast(split_part(
            (select rule_set.free_born_from from rule_set), '-', 2
        ) as integer)
    ), false) as b_list,
    coalesce(origin_is_ours, false) or months_club >= {{ months }} as hg_club,
    case
        when origin_is_ours and via_academy then 'academy'
        when origin_is_ours then 'youth-origin'
        when months_club >= {{ months }} then 'clock'
    end as hg_basis,
    (
        coalesce(origin_is_ours, false)
        or months_club >= {{ months }}
        or coalesce(origin_is_domestic, false)
        or months_domestic >= {{ months }}
    ) as hg_association,
    months_club,
    case
        when
            months_club < {{ months }}
            then round({{ months }} - months_club, 1)
    end as months_to_go,
    case
        when
            months_club < {{ months }}
            and snapshot_date
            + cast(
                ({{ months }} - months_club) * {{ var('days_in_month') }}
                as integer
            )
            <= window_to
            then
                snapshot_date
                + cast(
                    ({{ months }} - months_club) * {{ var('days_in_month') }}
                    as integer
                )
    end as hg_eta,
    snapshot_date <= window_to as window_open,
    origin_club,
    origin_nation,
    via_academy
from players
