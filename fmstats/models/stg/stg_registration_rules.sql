-- The squad-registration rule sets (a house rule the game does not model:
-- docs/danish-registration-rules.md, docs/english-registration-rules.md), one
-- row per rule set and range of tiers, from seeds/registration_rules.csv. A
-- career names its rule set in fmm.toml (stg_career.registration_rule_set);
-- the managed league's tier picks the row.
--   list_max        the registration list's cap; NULL = no cap
--   free_*          the list that does not count against it: players under
--                   free_under_age, i.e. born on or after free_born_from
--                   ('MM-DD') of the season's first calendar year less that
--                   age; with free_gk, every goalkeeper too
--   hg_*            the home-grown minimums on the list (overall, and trained
--                   at the club), and the nations whose clubs train a player
--                   home grown ('|'-separated; NULL = the managed club's own)
--   matchday_*      the matchday squad's substitutes, home-grown minimum and
--                   loan maximum; loan_max_per_club the most loans from one
--                   club
select
    rule_set,
    tier_from,
    tier_to,
    league_label,
    list_max,
    list_label,
    free_label,
    free_under_age,
    free_born_from,
    free_gk,
    hg_min,
    hg_club_min,
    hg_nations,
    matchday_subs,
    matchday_hg_min,
    matchday_loan_max,
    loan_max_per_club,
    min_matchday_age
from {{ source('raw', 'registration_rules') }}
