{# A player's moves: career-history lines, transfers, loans, contracts, spells. #}

{% docs fee_type %}
The fee code on a career-history line, decoded: `fee` (a fee, `fee_gbp`), `free`, `stay` (he
stayed on a free: a Bosman where the next line is another club), `loan` (on the borrowing club's
line), `contract_ended` (the contract ran out), `unknown` (a code not understood, as on an
academy's line). On a transfer, the selling club's line's code.
Synonyms: `fee_kind`.
{% enddocs %}

{% docs move_fee_type %}
How a dated move on the development chart was paid for: `fee` (a permanent transfer with a fee),
`free` (a free move), `none` (a graduation, or an internal move between our teams), `unknown`
(the history's fee code is not understood).
Synonyms: `site_player_moves.fee_type`.
{% enddocs %}

{% docs fee_label %}
The fee code as the profile shows it: the fee in pounds (`£1,250,000`), `loan`, `free`, `stay`
or `contract ended`; NULL for a code not understood.
{% enddocs %}

{% docs transfer_type %}
What kind of move it was: `permanent` (a fee above 0), `free` (a fee of 0: a free, a Bosman, a
contract run out, a free agent signed), `graduation` (from a club's youth side into its senior
side); NULL where the fee code is not understood.
{% enddocs %}

{% docs from_club_tid %}
The club he left. NULL for a free agent's signing. For an internal move on the development
chart (`site.player_moves`), the team he left (first team or reserves).
{% enddocs %}

{% docs to_club_tid %}
The club he joined. For an internal move on the development chart, the team he joined.
{% enddocs %}

{% docs youth_team_tid %}
The academy a move left, where it left one (its club is `from_club_tid`); NULL otherwise.
{% enddocs %}

{% docs to_line_index %}
The career-history line the move arrives at: the buying club's first line, or one past his last
line for a move only his newest snapshot shows (`is_from_snapshot`). With `person_id` it keys a
transfer.
{% enddocs %}

{% docs is_from_snapshot %}
The move is not in his career history yet (a move made during a season has no line for the
buying club until the season ends): his club on his newest snapshot differs from his last
line's.
{% enddocs %}

{% docs is_free_agent_signing %}
He had no club on `moved_after_date`; NULL where the move has no snapshot bounds.
Synonyms: `was_free_agent`.
{% enddocs %}

{% docs direction %}
Our side of a move: `in` to our club, `out` from it (club level: first team and reserves are one
club); NULL for a move that doesn't involve us.
{% enddocs %}

{% docs transfer_window %}
The window the move falls in: `summer` (June-September) or `winter` by the move date, else by the
first snapshot showing him at the new club; `undated` where neither is known.
{% enddocs %}

{% docs is_in_career %}
The move's season falls inside the career (a `site.snapshots` season). Earlier rows are the
history the save keeps for players still in it.
Synonyms: `in_career`.
{% enddocs %}

{% docs borrowing_club_tid %}
The club he is on loan at.
{% enddocs %}

{% docs borrowing_team_tid %}
The team that lists him on loan, else the loan line's team.
{% enddocs %}

{% docs parent_club_tid %}
The club that owns him while he is on loan: his record's club where a snapshot lists him on loan,
else the best of the rules in int.loan_spells.
{% enddocs %}

{% docs has_line %}
The loan has a loan line in his career history; false for a loan only a squad listing shows
(a loan made this season).
{% enddocs %}

{% docs first_team_tid %}
The team the contract names on its first snapshot (a move to the reserves keeps the contract).
{% enddocs %}

{% docs last_team_tid %}
The team the contract names on its last snapshot.
{% enddocs %}

{% docs end_reason %}
How the contract ended, read on `ended_by_date`: `renewed` (a new contract at the same club),
`transferred` (a contract at another club), `expired` (no contract, its expiry passed),
`released` (no contract, its expiry not reached), `retired` (no player record: retired or turned
to coaching); NULL while it is in force.
{% enddocs %}

{% docs spell_type %}
The kind of spell on the development chart: `at_club` (a run of consecutive snapshots on one
team's books), `loan_out` (a loan of ours with dates), `loan_in` (a loan to us), `injured`.
{% enddocs %}

{% docs move_type %}
The kind of dated move on the development chart: `transfer` (between clubs, with a known date) or
`internal` (between our first team and reserve side).
{% enddocs %}
