-- The squad-registration rules that apply to us on each snapshot, keyed
-- snapshot_date: the managed team's league, its tier and nation, and the row
-- of the career's rule set (stg_career.registration_rule_set,
-- stg_registration_rules; a house rule) whose tiers hold it, so a promotion
-- switches the rules. No row for a tier the rule set does not cover, or a
-- rule set of 'none'. u21_on is the last day a player must be under
-- b_list_under_age on to go on the free list: the day before he would turn it
-- if born on the rule set's free_born_from.
with snapshots as (
    select
        clubs.snapshot_date,
        snapshots.season,
        leagues.tier,
        clubs.league_name,
        clubs.nation,
        career.registration_rule_set
    from {{ ref('site_clubs') }} as clubs
    inner join {{ ref('stg_career') }} as career
        on clubs.team_tid = career.managed_club_tid
    inner join {{ ref('stg_snapshots') }} as snapshots
        on clubs.snapshot_date = snapshots.snapshot_date
    left join {{ ref('site_leagues') }} as leagues
        on
            clubs.snapshot_date = leagues.snapshot_date
            and clubs.league_cid = leagues.cid
)

select
    snapshots.snapshot_date,
    snapshots.tier,
    snapshots.league_name,
    snapshots.nation,
    rules.tier_from,
    rules.league_label,
    rules.list_max as a_list_max,
    rules.list_label,
    rules.free_label,
    rules.free_gk as is_goalkeeper_free,
    rules.hg_min,
    rules.hg_club_min,
    rules.free_under_age as b_list_under_age,
    rules.matchday_subs,
    rules.matchday_hg_min as matchday_home_grown_min,
    rules.matchday_loan_max,
    rules.loan_max_per_club,
    rules.min_matchday_age,
    cast(
        make_date(
            cast(snapshots.season as integer) - 1 - rules.free_under_age,
            cast(split_part(rules.free_born_from, '-', 1) as integer),
            cast(split_part(rules.free_born_from, '-', 2) as integer)
        )
        + to_years(rules.free_under_age)
        - interval 1 day as date
    ) as u21_on
from snapshots
inner join {{ ref('stg_registration_rules') }} as rules
    on
        snapshots.registration_rule_set = rules.rule_set
        and snapshots.tier between rules.tier_from and rules.tier_to
