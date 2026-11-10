{# Columns of the web app's presentation marts (models/site) that no other layer carries, and the
   awards and roles. #}

{% docs key %}
A setting's name in `site.config` (`default_method`, `familiarity_curve`, `familiarity_floor`, the
`career_*` and `immersion_*` settings, `min_familiarity`, `fallback_formation`).
{% enddocs %}

{% docs value %}
A setting's value in `site.config`, as text.
{% enddocs %}

{% docs method %}
A weight set's name (`seeds/role_weights.csv`): the career's `rating_method` in `fmm.toml` picks
one.
{% enddocs %}

{% docs role %}
A weight set's role code (`GK`, `CB`, `LB`, `DM`, `CM`, `AMC`, `ST`, ...): the role a position
is rated in (`site.position_roles`) and the weights belong to (`site.role_weights`).
{% enddocs %}

{% docs rating_role %}
The role a match rating is compared within for `rating_adj` (`var('rating_roles')`:
`Centre-back`, `Full-back`, `Wing-back`, `DM`, `Central mid`, `Wide mid`, `Attacking mid`,
`Winger`, `Forward`, `GK`), from the position he played; NULL for a substitute.
{% enddocs %}

{% docs attribute %}
An attribute's name, as the displayed attributes are named (`Crossing`, `Pace`, ...).
{% enddocs %}

{% docs weight %}
The attribute's weight in the role, in the weight set.
{% enddocs %}

{% docs formation_order %}
The formation's place in `var('formation_slots')`, from 1.
{% enddocs %}

{% docs position_order %}
The position's place within its formation in `var('formation_slots')`, from 1.
{% enddocs %}

{% docs slots %}
How many start at the position in the formation (the club's formation on `site.loan_outlook`).
{% enddocs %}

{% docs rank %}
His place among the club's natural players at the position (familiarity
`var('loan_outlook').min_familiarity` or more), ordered by ability, 1 first choice: he starts if
`rank` <= `slots`.
{% enddocs %}

{% docs line %}
The Level %ile (see `level`) of the weakest starter he would have to beat: the `slots`-th best
natural player at the club other than him. NULL where the club has fewer, so he walks in.
{% enddocs %}

{% docs n_players %}
The players the row counts: on `site.loan_outlook`, the other players listing the position in
the division (the pool `level` is a share of); on `site.forecast`, the players in the cell;
on `site.clubs`, the players whose own record names the team.
{% enddocs %}

{% docs n_pairs %}
The pairs of a player's snapshots, a year apart, the row is computed over.
{% enddocs %}

{% docs p25 %}
The 25th percentile of the row's distribution (on `site.forecast`, of the values reached at
`horizon_age`; on `site.age_curve`, of the points gained in a year).
{% enddocs %}

{% docs median %}
The median of the row's distribution (as `p25`).
{% enddocs %}

{% docs mean %}
The mean of the row's distribution (as `p25`).
{% enddocs %}

{% docs p75 %}
The 75th percentile of the row's distribution (as `p25`).
{% enddocs %}

{% docs value_now %}
The attribute's value at `age_now`, the forecast cell's starting point.
{% enddocs %}

{% docs bucket %}
Whether to trust an attribute's forecast cells: `fixed` where it doesn't move between two exact
reads a year apart, `unmodelled` where too few exact pairs exist or the decoded reads grow at more
than `max_ratio` times (or less than 1/`max_ratio` of) the exact ones (`var('forecast')`), else
`forecastable`.
{% enddocs %}

{% docs n_games %}
The managed team's home matches with an attendance in the season (friendlies' 0 left out).
{% enddocs %}

{% docs average_attendance %}
The average home crowd in the season, rounded to a whole number.
{% enddocs %}

{% docs min_attendance %}
The smallest home crowd in the season.
{% enddocs %}

{% docs max_attendance %}
The largest home crowd in the season.
{% enddocs %}

{% docs is_through %}
We won the knockout tie the match belongs to, once it is decided; NULL outside a knockout stage
or before it is decided.
{% enddocs %}

{% docs a_list_max %}
The most players the A-list holds (`var('registration')`, a house rule).
{% enddocs %}

{% docs home_grown_min %}
The fewest home-grown players the squad must have (trained in the nation); 0 below the top
`hg_tiers` tiers (`var('registration')`, a house rule).
{% enddocs %}

{% docs home_grown_club_min %}
The fewest players trained at the club the squad must have; 0 below the top `hg_tiers` tiers.
{% enddocs %}

{% docs b_list_under_age %}
A player under this age on `b_list_age_date` goes on the B-list (`var('registration')`).
{% enddocs %}

{% docs min_matchday_age %}
The youngest age allowed on a matchday squad (`var('registration')`).
{% enddocs %}

{% docs entry_name %}
The player's full name as the scrapbook entry stores it.
{% enddocs %}

{% docs is_final %}
The World Best XI pool's season has ended, so the pool no longer changes (the All-Time pool is
always final).
{% enddocs %}

{% docs is_inferred %}
The role's name was given by elimination (the role left in its position block, placed by its
holders' attributes), not read off a Scrapbook Profile or the Training page.
{% enddocs %}

{% docs loan_club_tid %}
The club the player was on loan at on the scrapbook entry's date (the entry's club marker is
`[parent][loan club]`); NULL when he was not on loan.
{% enddocs %}
