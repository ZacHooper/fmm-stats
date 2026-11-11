{# Clubs and teams, nations, cities and stadiums: names, records and what they hold. #}

{% docs name %}
The row's subject's name as the game shows it, the latest the store holds: a person's (from his
latest scrapbook entry where we have one), a team's long name, a club's (its first team's), a
competition's, a nation's, a stage's or round's from its rules, a stadium's, an award's.
{% enddocs %}

{% docs team_type %}
What kind of side the team is: `first`, `reserve`, `b_team` (a second side in the senior
pyramid, Las Palmas C), `national` or `national_u21` (`var('team_types')`, `var('b_team')`).
{% enddocs %}

{% docs club_type %}
The team record's own type code: 0 a club side (first teams and B sides), 1 a national team, 2 a
reserve side, 3 a U21 national team. `team_type` is the decoded form.
{% enddocs %}

{% docs is_first_team %}
The team is its club's first team: the team that owns the club (`team_tid` = `club_tid`).
{% enddocs %}

{% docs is_managed %}
The team is the one the career manages (`managed_tid` in `fmm.toml`).
{% enddocs %}

{% docs is_managed_club %}
The team belongs to the club the career manages (its first team or reserve side).
{% enddocs %}

{% docs is_listed %}
The team is worth naming in the web app's club pickers: it has a rated player, we played it that
season, or it is on a career line of a player with two lines or more. The rest are the save's
empty slots (national sides, reserve sides with no squad, clubs no player passes through).
{% enddocs %}

{% docs colours %}
The club's six colours from its record, as hex RGB strings (decoded from RGB555), a JSON list.
Which slot is which is not mapped; `shirt_colours` is the usable pair.
{% enddocs %}

{% docs kits %}
The club's six kits, each a list of ten hex RGB colours (a JSON list of lists): slot 0 home, 1
away, 2 third (a club with no third kit still fills it with a black-and-white default); slots
3-5 are not identified.
{% enddocs %}

{% docs shirt_colours %}
The home shirt as two hex colours, main first: the home kit's second slot, then its first or
third, whichever differs from the main colour by `var('shirt_colour_min_distance')`; a plain
shirt is the main colour twice. A club in the game's stock kit (`var('default_kit')`) has its
name colours instead.
{% enddocs %}

{% docs affiliates %}
The club record's affiliation links, as stored: a list of `{club1_tid, club2_tid, start_day,
start_year, end_day, end_year}`, empty with none. Unverified: that a day is the day of the year
(club_records stores its dates so; the affiliation dates were not checked on a screen).
{% enddocs %}

{% docs league_nation_id %}
The nation whose league the club plays in (Cardiff City: England), where `nation_id` is its
home nation (Wales).
{% enddocs %}

{% docs status %}
The team's status as its record stores it, 0-3: 1 is Professional (Club Information); 0 on every
national side. The other values are not named.
{% enddocs %}

{% docs squad_status %}
Where the player stands in our squad: `Loan` out on loan, `Reserve` listed by our reserve side
only, else `First team`.
Synonyms: `site_squad.status`.
{% enddocs %}

{% docs training_facilities %}
Training Facilities, 1-20 (Club Information). A reserve side has its club's (its own record
holds a default). fmm-editor names this byte `academy`, wrongly.
{% enddocs %}

{% docs youth_facilities %}
Youth Facilities, 1-20 (Club Information). A reserve side has its club's. fmm-editor names this
byte `facilities`, wrongly.
{% enddocs %}

{% docs squad_size %}
The players the team's own squad array lists: its filled slots (out of 40). Not the players
whose own record names the team (block `n_players`), a different figure for a team with loans.
{% enddocs %}

{% docs staff_size %}
The coaching staff the team's record lists (its staff array, which leaves out the manager).
{% enddocs %}

{% docs capacity %}
The stadium's capacity on the snapshot.
{% enddocs %}

{% docs expansion_capacity %}
The most the stadium can be expanded to.
{% enddocs %}

{% docs latitude %}
The city's latitude in degrees, as stored.
{% enddocs %}

{% docs longitude %}
The city's longitude in degrees, as stored.
{% enddocs %}

{% docs attraction %}
The game's 0-20 rating of the city.
{% enddocs %}

{% docs club %}
A club's name. On `site.places`, the team's own name; on a career line, the team's, or for a
youth side (which the save doesn't name) its club's, `#<tid>` for a tid the save has no record
for.
{% enddocs %}

{% docs stadium %}
The stadium's name on the snapshot.
{% enddocs %}

{% docs opponent %}
The opposing team's name.
{% enddocs %}

{% docs nation %}
A nation's name: on a team or league row, the league's nation.
Synonyms: `site_players.nationality`.
{% enddocs %}

{% docs nationality %}
The nation's demonym as the game stores it (Danish, English).
{% enddocs %}

{% docs capital_city_id %}
The nation's capital. NULL where the save names none.
{% enddocs %}

{% docs national_stadium_id %}
The nation's national stadium. NULL where the save names none.
{% enddocs %}

{% docs rival_nation_id %}
The nation the game names as this one's rival.
{% enddocs %}

{% docs rival %}
The name of the nation's rival.
{% enddocs %}

{% docs is_ranked %}
The nation has a world ranking.
{% enddocs %}

{% docs world_ranking %}
The nation's world ranking as stored, from 0 (the top); `world_rank` is it + 1, as the game shows
it.
{% enddocs %}

{% docs world_rank %}
The nation's world ranking as the game shows it, 1 the top.
{% enddocs %}

{% docs ranking_points %}
The nation's world ranking points.
{% enddocs %}

{% docs ranking_history %}
The nation's world ranking history, a list, oldest first, as stored.
{% enddocs %}

{% docs coefficient_history %}
The nation's continental coefficient per season, a list, oldest first; the last entry is the
season in progress (0 until it scores). Only European nations have one that changes. The list
moves along one place when a season closes.
{% enddocs %}

{% docs coefficient %}
The sum of `coefficient_history`.
{% enddocs %}

{% docs coefficient_5 %}
The sum of the five newest completed seasons of `coefficient_history` (the UEFA association
ranking's figure); NULL with one entry or none.
{% enddocs %}

{% docs coefficient_season %}
The season (end year) of the newest completed entry of `coefficient_history`, the second to last:
the year of the latest snapshot, up to this one, on which the list moved along. NULL before any
such move is on record.
{% enddocs %}

{% docs is_coefficient_live %}
The nation's coefficient history changes somewhere in the store. Some never do (every African
nation's): those are the game's starting values, which it doesn't update.
{% enddocs %}

{% docs is_uefa %}
The nation is a UEFA member (continent `var('uefa_continent_id')`).
{% enddocs %}

{% docs uefa_rank %}
The nation's place in the UEFA association ranking: UEFA members ranked by `coefficient_5`, ties
to the better newest completed season, then name. NULL outside UEFA or with no completed
season.
{% enddocs %}

{% docs languages %}
The languages the nation speaks, best first: a list of `{language, proficiency}`, proficiency
0-100 (the highest where the save lists a language twice).
{% enddocs %}
