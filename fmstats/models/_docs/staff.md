{# Staff: the staff record (docs/parser/staff.md) and staff spells. #}

{% docs has_staff_record %}
The save holds a staff record for the person (joined on his record's `id2`); without one, every
staff value is NULL.
{% enddocs %}

{% docs home_reputation %}
The staff member's home reputation, 50-10,000, as stored.
{% enddocs %}

{% docs current_reputation %}
The person's current reputation as stored, up to 10,000.
{% enddocs %}

{% docs world_reputation %}
The person's world reputation as stored. A staff member's sets the profile's Reputation tier
(`reputation_tier`). A player's runs to 65,534 on a few records, out of the 10,000 scale
(unverified: what those values mean).
{% enddocs %}

{% docs reputation_tier %}
The reputation the game's staff profile shows: `Regional`, `National` or `Continental`, from
`world_reputation` (`var('staff_tier_bands')`: cuts at 3,000 and 5,900; the second edge is
bracketed, not measured). NULL without a staff record.
{% enddocs %}

{% docs attacking_intent %}
A hidden 1-20 value that sets the manager's displayed Style (`style`).
{% enddocs %}

{% docs style %}
The manager's Style as the game's profile shows it: `Defensive` (attacking_intent up to 7),
`Normal` (up to 13) or `Attacking` (`var('staff_style_bands')`, checked on fourteen managers).
NULL without a staff record.
{% enddocs %}

{% docs financial_control %}
Financial control, 1-20.
{% enddocs %}

{% docs outfield_coaching %}
Outfield coaching, 1-20.
{% enddocs %}

{% docs goalkeeping_coaching %}
Goalkeeping coaching, 1-20; a few records read 51-99, carried as stored (not a 1-20 rating).
{% enddocs %}

{% docs discipline %}
Discipline, 1-20.
{% enddocs %}

{% docs judging_ability %}
Judging player ability, 1-20.
{% enddocs %}

{% docs judging_potential %}
Judging player potential, 1-20.
{% enddocs %}

{% docs people_management %}
People management, 1-20.
{% enddocs %}

{% docs motivating %}
Motivating, 1-20.
{% enddocs %}

{% docs tactical_knowledge %}
Tactical knowledge, 1-20.
{% enddocs %}

{% docs youth_coaching %}
Youth coaching, 1-20.
{% enddocs %}

{% docs hidden_s18 %}
Unverified: a hidden 1-20 staff value at record offset +18, not identified.
{% enddocs %}

{% docs hidden_s20 %}
Unverified: a hidden 1-20 staff value at record offset +20, not identified.
{% enddocs %}

{% docs hidden_s24 %}
Unverified: a hidden 1-20 staff value at record offset +24, not identified.
{% enddocs %}

{% docs hidden_s26 %}
Unverified: a hidden 1-20 staff value at record offset +26, not identified.
{% enddocs %}

{% docs hidden_s27 %}
Unverified: a hidden 1-20 staff value at record offset +27, not identified; it reads 1-4 on most
staff, the most distinctive of the six.
{% enddocs %}

{% docs hidden_s28 %}
Unverified: a hidden 1-20 staff value at record offset +28, not identified.
{% enddocs %}

{% docs formation_preferred %}
The manager's preferred formation as the save codes it (`formation_preferred_name` names it);
NULL without a staff record.
{% enddocs %}

{% docs formation_attacking %}
The formation the manager uses to attack, as the save codes it (`formation_attacking_name`
names it).
{% enddocs %}

{% docs formation_defensive %}
The formation the manager uses to defend, as the save codes it (`formation_defensive_name`
names it).
{% enddocs %}

{% docs staff_role %}
The staff member's job on the team: `manager` or `staff`. The save names no job: the manager is
the staff member with a staff record on the team's books whom its staff array doesn't list (the
highest home reputation where more than one isn't), everyone else `staff`.
Synonyms: `fact_staff_spell.role`.
{% enddocs %}

{% docs n_manager_candidates %}
How many staff members on the team's books its staff array doesn't list, of whom the manager is
picked.
Synonyms: `manager_candidates`.
{% enddocs %}
