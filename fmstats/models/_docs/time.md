{# Dates, seasons and the snapshot bounds of a spell. #}

{% docs snapshot_date %}
The save a row was read from, by its in-game date (the save header's date, never the last
match's). Every save loaded into the store is one snapshot; several can fall in one season.
{% enddocs %}

{% docs season %}
A campaign, by its end year (2023/24 is 2024). A date's season follows the career's rollover
day (`fmm.toml`; macros/season.sql): on or after it, the next year's. On a career-history line,
a loan or a transfer it is the season the game labels the line with; on a World Best XI pool,
the season the pool is for.
{% enddocs %}

{% docs competition_season %}
A competition's own season label, from the fixture list: the year the season starts (2025 for
a 2025/26 league and for a calendar-year 2025 one). Not `season`: a 2025/26 league is
competition_season 2025 and season 2026.
{% enddocs %}

{% docs match_date %}
The day the match is (or was) played, from the world fixture list.
{% enddocs %}

{% docs first_seen_date %}
The first snapshot that shows the row's subject (a person, a contract, a spell, a loan).
{% enddocs %}

{% docs last_seen_date %}
The last snapshot that shows the row's subject: on a dimension, the snapshot its static values
are taken from; on a spell or contract, the last snapshot it was in force.
{% enddocs %}

{% docs ended_by_date %}
The store's next snapshot after `last_seen_date`: the first that no longer shows the spell or
contract. The real end lies between the two. NULL while it runs on the newest snapshot.
{% enddocs %}

{% docs is_current %}
The row holds on the store's newest snapshot: a snapshot row taken from it, or a spell,
contract or SCD interval still in force on it.
{% enddocs %}

{% docs is_latest %}
The newest row of its series: on `site.snapshots` the store's newest snapshot; on
`mart.standings` the stage's latest matchday, so filtering on it gives the current table.
{% enddocs %}

{% docs valid_from_date %}
The first snapshot of the SCD interval: the state on this row holds from this snapshot.
Synonyms: `valid_from`.
{% enddocs %}

{% docs valid_to_date %}
The last snapshot of the SCD interval: the state holds through this snapshot (inclusive); the
next interval starts on the following snapshot.
Synonyms: `valid_to`.
{% enddocs %}

{% docs start_date %}
The first day of the spell. For an injury, its first injured week in Player Progress, so the
true start lies within a week of it. For a loan, its first week flagged on loan, and only for a
loan out of the club we manage; NULL for every other loan (the save gives no loan dates).
{% enddocs %}

{% docs end_date %}
The last day of the spell: an injury's last injured week, a loan of ours' last week flagged on
loan (NULL otherwise). The true end lies within a week of it.
{% enddocs %}

{% docs from_date %}
The first day of a spell on the development chart (`site.player_spells`): the day his record
says he joined (`at_club`, where it lies between the run's first snapshot and the one before),
the loan's start, the first snapshot listing a loan to us, or the injury's first week.
{% enddocs %}

{% docs to_date %}
The last day of a spell on the development chart; NULL while it runs on the newest snapshot.
{% enddocs %}

{% docs weeks %}
The spell's length: how many weekly Player Progress rows in the run are flagged. A gap shorter
than `var('progress_spells')`' `gap_days` does not end a run, so this can be fewer than the
weeks from `start_date` to `end_date`.
{% enddocs %}

{% docs label %}
The snapshot's label, the save's file name without its extension
(`<career>-<YYYY-MM-DD>[-<tag>]`).
{% enddocs %}

{% docs through_date %}
The latest match date the standings row's totals include.
{% enddocs %}

{% docs first_match_date %}
The date of the first match (scheduled or played) of the row's subject: a team's in a
competition season, or a tie's first leg.
{% enddocs %}

{% docs last_match_date %}
The date of the last match (scheduled or played) of the row's subject: a team's in a
competition season, or a tie's last leg.
{% enddocs %}

{% docs entry_date %}
The date of the scrapbook entry: the Scrapbook Profile is the player as of this day.
{% enddocs %}

{% docs scrapbook_entry_date %}
The date of the scrapbook entry the player's name and value come from, where a fresh one
exists (within `var('scrapbook_max_age_days')` of the snapshot); NULL otherwise. Only our own
squad has entries.
{% enddocs %}

{% docs joined_date %}
The date his record says he joined his current club. The game resets it when a player returns
from a loan, and the day-one database holds dates up to months ahead, so it is not always the
transfer's date (`fact_transfer.move_date` keeps it only where it fits the move).
{% enddocs %}

{% docs move_date %}
The day the player joined the buying club, from his record's joined date, where it lies
between the move's snapshot bounds and is the move's own (NULL where the club loaned him out
in between, or the date lies more than a season from the move's season). An internal move
between our first team and reserves (`site.player_moves`) is dated by its first snapshot.
{% enddocs %}

{% docs moved_after_date %}
For a move made while the store was watching: the last snapshot showing the player at his old
club (or without one). The move lies after it. NULL for a move the history shows from before.
Synonyms: `moved_after`.
{% enddocs %}

{% docs moved_by_date %}
For a move made while the store was watching: the first snapshot showing the player at the
buying club. The move lies on or before it. NULL for a move the history shows from before.
Synonyms: `moved_by`.
{% enddocs %}

{% docs birth_date %}
The person's date of birth, as the save stores it; part of `person_id`.
Synonyms: `dob`.
{% enddocs %}

{% docs contract_start_date %}
The start date of the player's current contract, as stored (the day it was signed). NULL with
no contract.
Synonyms: `contract_start`.
{% enddocs %}

{% docs contract_expiry_date %}
The expiry date of the player's current contract, as stored. NULL with no contract.
Synonyms: `contract_expiry`.
{% enddocs %}

{% docs signed_date %}
The day the contract was signed, which is the day it starts: the stored start date, except
NULL where that is later than the first snapshot holding the contract (the day-one database
holds start dates months ahead on contracts already in force, which are not when they were
signed). `stored_signed_date` keeps the stored value either way.
{% enddocs %}

{% docs stored_signed_date %}
The contract's start date exactly as stored, including the day-one database's future dates
that `signed_date` drops.
{% enddocs %}

{% docs expiry_date %}
The contract's expiry date as stored; read on its first (`first_expiry_date`) and last
(`last_expiry_date`) snapshot, since a few contracts change expiry under one start date.
{% enddocs %}

{% docs b_list_age_date %}
The date the B-list age is taken on: 1 January of the year before the season's end year, the
last new year before the season's second calendar year (`var('registration')`, a house rule).
Synonyms: `u21_on`.
{% enddocs %}

{% docs home_grown_date %}
The day he reaches `var('home_grown_months')` months with us if he stays, where that lies inside
his home-grown window; NULL when he already has them or would run out of window first.
Synonyms: `hg_eta`.
{% enddocs %}
