-- Every tier's row of the career's squad-registration rule set (a house rule:
-- stg_registration_rules), keyed tier_from: what the Squad page's "Count as"
-- picker recounts the squad against, so a club below a tier can plan for the
-- rules above it. Empty for a career whose rule set is 'none'.
select
    rules.tier_from,
    rules.tier_to,
    rules.league_label,
    rules.list_max as a_list_max,
    rules.list_label,
    rules.free_label,
    rules.free_under_age as b_list_under_age,
    rules.free_gk as is_goalkeeper_free,
    rules.hg_min,
    rules.hg_club_min,
    rules.matchday_subs,
    rules.matchday_hg_min as matchday_home_grown_min,
    rules.matchday_loan_max,
    rules.loan_max_per_club,
    rules.min_matchday_age
from {{ ref('stg_registration_rules') }} as rules
inner join {{ ref('stg_career') }} as career
    on rules.rule_set = career.registration_rule_set
