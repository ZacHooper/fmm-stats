{# Regional strength: tier levels, club Elo and the region scores (fact_tier_level_snapshot, fact_club_elo, fact_club_region_snapshot, fact_region_*). #}

{% docs level_ca %}
The tier's level: the median CA of its teams' best var('region_regulars') players, every
nationality counted. Warehouse-only, like CA: presentation carries the weight and counts made
from it, never the number.
{% enddocs %}

{% docs is_scored %}
The tier counts in the regional scores: its leagues have matches in the store, which the
game holds only for the leagues it plays out.
{% enddocs %}

{% docs tier_weight %}
What an appearance in the tier is worth in the regional appearance score: the tier's level
above the first unscored tier's (0 where there is none), over the lowest scored tier's, so the
lowest scored tier weighs 1. NULL on an unscored tier.
{% enddocs %}

{% docs rating_event %}
What moved the rating: `seed` (the team's first appearance in the home nation's leagues) or
`match`.
{% enddocs %}

{% docs rating_date %}
The day of the rating event: the match date, or a seed's snapshot.
{% enddocs %}

{% docs elo %}
The team's Elo rating after the row's event (fact_club_elo), or as of the row's snapshot. A
team starts at a seed set by its tier's level and moves with each match against another rated
team; see fact_club_elo.py for the formula and var('region_elo') for its settings.
{% enddocs %}

{% docs elo_before %}
The team's Elo rating before the match; NULL on a seed.
{% enddocs %}

{% docs event_order %}
The rating event's place in the team's sequence, from 0 (its seed).
{% enddocs %}

{% docs elo_mean %}
The mean Elo of the region's teams in the scored tiers.
{% enddocs %}

{% docs elo_median %}
The median Elo of the region's teams in the scored tiers.
{% enddocs %}

{% docs elo_top3 %}
The mean Elo of the region's best three teams in the scored tiers (fewer where it has fewer).
{% enddocs %}

{% docs elo_p75_share %}
The share of the region's teams in the scored tiers rated at or above the nation's 75th
percentile Elo, 0 to 1.
{% enddocs %}

{% docs youth_facilities_median %}
The median youth facilities (1-20) of the region's teams in the scored tiers.
{% enddocs %}

{% docs n_good_youth_facilities %}
The region's teams in the scored tiers with youth facilities of var('region_facilities_good_min')
or more (three stars or more).
{% enddocs %}

{% docs training_facilities_median %}
The median training facilities (1-20) of the region's teams in the scored tiers.
{% enddocs %}

{% docs n_good_training_facilities %}
The region's teams in the scored tiers with training facilities of
var('region_facilities_good_min') or more (three stars or more).
{% enddocs %}

{% docs level_tier %}
The highest scored tier whose level (fact_tier_level_snapshot.level_ca) the player reaches: 1
is a top-flight regular's level or better. NULL below the lowest scored tier's level.
{% enddocs %}

{% docs is_under_21 %}
The player is under var('region_u21_age') on the snapshot.
{% enddocs %}

{% docs age_group %}
Which players a count covers: `all`, or `under_21`.
{% enddocs %}

{% docs nation_share %}
The region's part of the nation's total for the row's measure, 0 to 1.
{% enddocs %}

{% docs nation_share_index %}
The region's share over its share on the first snapshot (or in the first season): 1 is
unchanged, 1.10 a tenth more of the nation's total than at the start.
{% enddocs %}

{% docs is_live %}
The row's season is the latest snapshot's, still being played: its figures grow with each
save.
{% enddocs %}

{% docs weighted_appearances %}
Appearances in the scored tiers, each weighted by its tier's tier_weight.
{% enddocs %}

{% docs appearances_by_tier %}
The row's appearances split by tier: a list of `{tier, appearances}`, top tier first.
{% enddocs %}
