{# Ids and keys: what each id names, its range and where NULL comes from. One block per
   canonical column name (fmstats/AGENTS.md, column naming convention). #}

{% docs person_id %}
A person, across every snapshot: `'<tid>-<dob>'` (macros/person_id.sql). The game hands a
retired person's tid to a newgen, so the tid alone would join two careers; the date of birth
separates them (`'?'` where it is unknown). Keys `dim_person`. NULL on a match or award row for
a player no snapshot holds a person record for (reserve games' anonymous fillers; a past
award winner who left the game's database before the first save).
{% enddocs %}

{% docs tid %}
A person's id in the save on that snapshot: his slot in the person table. Not stable across a
career: the game reuses a retired person's tid for a newgen, so join people on `person_id` and
use the tid only within one snapshot (or to read a scrapbook or match line, which store it).
{% enddocs %}

{% docs team_tid %}
A team: the side that plays (a first team, reserve side, B side, national or national U21
side), keyed in `dim_team`. Every team is stored as a whole club-shaped record, and its tid is
that record's slot. A youth side has no record; where a career line names one, its tid is
`var('youth_tid_base')` minus its club's tid (Frem 346 -> 65189). Never above
`var('match_id_tid_base')` - 1 (tested on `dim_match`). A club's tid is its first team's, so a
club is a team too.
Synonyms: `site_loan_outlook.club_tid`, `site_player_spells.club_tid`.
{% enddocs %}

{% docs club_tid %}
A club: the first team's tid, which owns itself and its reserve, B and youth sides
(`dim_team.club_tid`, keyed in `dim_club`). On a player's or staff member's row it is the club
that owns the team whose books he is on. A tid the save holds no record for (a career line at a
club the save doesn't keep) stays as stored.
{% enddocs %}

{% docs cid %}
A competition: its slot in the competition table, keyed in `dim_competition`. Stable across
snapshots (`uid` is the database id).
{% enddocs %}

{% docs match_id %}
A match: its date and its two teams packed into one BIGINT, `yyyymmdd * 100000^2 + home tid *
100000 + away tid` (macros/match_id.sql), so 2027-07-28 Salzburg (125) v Frem (346) is
202707280012500346. Unique, the same in every snapshot and rebuild, sorts by date. Keys
`dim_match`.
{% enddocs %}

{% docs nation_id %}
A nation: its slot in the nation table, keyed in `dim_nation`.
{% enddocs %}

{% docs city_id %}
A city: its slot in the city table, keyed in `dim_city`.
{% enddocs %}

{% docs stadium_id %}
A stadium: its slot in the stadium table, keyed in `dim_stadium`. On a team's row, the team's
own ground, else its club's (a reserve side stores none).
{% enddocs %}

{% docs region_id %}
The region the city lies in, as the save numbers it; NULL where the record names none
(0xFFFF). No region table is read, so the id is not resolved to a name.
{% enddocs %}

{% docs continent_id %}
The nation's continent as the save codes it; NULL where it holds none. 2 is Europe
(`var('uefa_continent_id')`): UEFA's members. The other codes are not named.
{% enddocs %}

{% docs uid %}
The game's database id of the row's subject (city, competition or stadium), as stored. Unlike
the slot id, it is the game's own identity, but nothing joins on it here.
{% enddocs %}

{% docs role_id %}
A player role (Poacher, Full-Back, ...) by the id the game uses in a training Focus Role and on a
Scrapbook Profile (`seeds/roles.csv`). The ids run in position order: 0-1 goalkeeper, 2 sweeper,
3-4 full-back, 5-7 centre-back, 8-12 wide, 13-17 central midfield, 18-24 striker; 25-32 are a
second set.
{% enddocs %}

{% docs award_id %}
An award the save records, from `var('awards')`: `world_best_xi` (a season's World Best XI pool)
or `world_best_xi_all_time` (the All-Time pool).
{% enddocs %}

{% docs event_type_code %}
A match event's type as the save codes it (1 goal, 2 own goal, 3 penalty, 4 missed penalty, 5
red card, 6 injury, 7/8 shoot-out goal/miss, 41 disallowed goal; `seeds` name the rest or leave
them NULL). Keys `dim_event_type`.
{% enddocs %}

{% docs event_index %}
The event's place in its match's event list, from 0, in the order the save stores them
(chronological).
{% enddocs %}

{% docs tie_id %}
A knockout tie: `'<cid>-<competition_season>-<stage_index>-<round_index>-<lower tid>-<higher
tid>'`, so both legs of a two-legged tie share it. NULL for a match outside a labelled knockout
round. Keys `mart.tie_results`.
{% enddocs %}

{% docs stage_index %}
A stage's place in its competition season's rules, from 0 (the first stage). With `cid` and
`competition_season` it keys `dim_stage`. NULL on a match whose stage is not labelled.
{% enddocs %}

{% docs round_index %}
A round's place in its knockout stage, from 0. With the stage's key it keys `dim_round`. NULL
outside a knockout stage.
{% enddocs %}

{% docs stage_key %}
The fixture list's own id for a stage within a competition season; a group stage has one per
group, so in `mart.standings` it names the group. A league keeps its stage_key from season to
season.
{% enddocs %}

{% docs slot %}
The player's place in the team's squad array, from 0, as the save stores it (the array has 40
fixed slots; empty slots hold no row).
{% enddocs %}

{% docs line_index %}
The line's place in the player's career history, from 0 (his oldest line any snapshot holds).
Lines are unioned across snapshots, so the index is stable even after the game drops a
player's oldest lines (int.player_career_lines).
{% enddocs %}
