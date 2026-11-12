-- The squad-registration rule sets (stg_registration_rules) are well formed:
--   overlap         two rows of one rule set share a tier, so a league would
--                   match both
--   empty range     tier_from is after tier_to
--   per-set rule    the free-list age and cut-off and the home-grown nations
--                   differ between a rule set's rows; site_registration reads
--                   them once per rule set, so a player's verdict cannot
--                   depend on the tier
--   bad cut-off     free_born_from is not a 'MM-DD' day
-- One row per offending row, or pair of rows, or rule set.
with rules as (
    select * from {{ ref('stg_registration_rules') }}
)

select
    'overlap' as check_name,
    a.rule_set,
    a.tier_from
from rules as a
inner join rules as b
    on
        a.rule_set = b.rule_set
        and a.tier_from < b.tier_from
        and a.tier_to >= b.tier_from
union all
select
    'empty range' as check_name,
    rule_set,
    tier_from
from rules
where tier_from > tier_to
union all
select
    'per-set rule' as check_name,
    rule_set,
    null as tier_from
from rules
group by rule_set
having
    count(distinct free_under_age) > 1
    or count(distinct free_born_from) > 1
    or count(distinct coalesce(hg_nations, '')) > 1
union all
select
    'bad cut-off' as check_name,
    rule_set,
    tier_from
from rules
where
    try_strptime('2001-' || free_born_from, '%Y-%m-%d') is null
