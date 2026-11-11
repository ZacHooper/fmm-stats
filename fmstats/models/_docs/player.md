{# A person and a player: bio, standing on a snapshot, contract, training, positions and the
   web app's derived readings of them. The attributes are in attributes.md. #}

{% docs age %}
Age in whole years. On a snapshot or registration row, on the snapshot's date; on a transfer, on
the move's date (the window's date standing in where there is none); on a scrapbook entry, the
age it stores, which can lag a birthday by a day or two; on `site.age_curve`, the age at the
start of the year measured.
{% enddocs %}

{% docs ethnicity %}
Unverified: a small code from the person record (0-10), named after fmm-editor's field; what
each value means is not known.
{% enddocs %}

{% docs height_cm %}
Height in cm, from the latest snapshot holding it.
{% enddocs %}

{% docs weight_kg %}
Weight in kg, from the latest snapshot holding it.
{% enddocs %}

{% docs foot_left %}
How good his left foot is, 1-20 (20 a natural; the game shows `Left Only`, `Either` and so on
from the pair).
{% enddocs %}

{% docs foot_right %}
How good his right foot is, 1-20.
{% enddocs %}

{% docs squad_number %}
His squad number at his club on the snapshot; 0 for none.
{% enddocs %}

{% docs preferred_squad_number %}
The squad number he prefers, as his record stores it; 0 for none.
{% enddocs %}

{% docs nationality_id %}
His (first) nationality.
{% enddocs %}

{% docs second_nationality_id %}
His other nationality; NULL for none.
{% enddocs %}

{% docs origin_team_tid %}
The team of the oldest career-history line with a club that any snapshot holds for him (a
first, reserve or B side, or a youth side): where he came from. NULL for a person never at a
club. That line is his first only where no snapshot had yet dropped any.
{% enddocs %}

{% docs origin_club_tid %}
The club that owns `origin_team_tid` (a youth side counts for the club whose academy it is), so a
club's own products have origin_club_tid = that club.
{% enddocs %}

{% docs origin_youth_team_tid %}
The academy he came out of where `origin_team_tid` is a youth side; NULL otherwise.
{% enddocs %}

{% docs origin_season %}
The season of his origin line (see `origin_team_tid`).
{% enddocs %}

{% docs is_capital_eligible %}
His origin club is on the career's signing list (`eligible_origin_clubs` in `fmm.toml`, a
house rule: Frem's Copenhagen region, Truro's open counties); false with no origin club or no
rule (`site.players`: NULL with no origin club). The name is Frem's; the rule is any career's.
Synonyms: `capital_eligible`.
{% enddocs %}

{% docs is_goalkeeper %}
His goalkeeper familiarity is 20.
{% enddocs %}

{% docs has_attributes %}
The save holds an attribute record for him (every player row in the snapshot facts does).
{% enddocs %}

{% docs ca %}
Current ability, 0-200 as stored. Never shown to a player with `hide_ability` (the immersion
rule): presentation uses `positions`' Level %ile instead. Staff have one too.
{% enddocs %}

{% docs pa %}
Potential ability, as stored (up to 200). Hidden under the immersion rule, as `ca` is.
{% enddocs %}

{% docs is_international_retired %}
His record's international-retirement flag.
Synonyms: `international_retired`.
{% enddocs %}

{% docs international_caps %}
Senior international caps, from his person record.
{% enddocs %}

{% docs international_goals %}
Senior international goals.
{% enddocs %}

{% docs u21_caps %}
U21 international caps.
{% enddocs %}

{% docs u21_goals %}
U21 international goals.
{% enddocs %}

{% docs is_value_estimated %}
`value` is the model's estimate, the save stating none for him (he is not in our squad, or his
scrapbook entry is stale).
Synonyms: `value_is_estimated`.
{% enddocs %}

{% docs is_value_in_trusted_band %}
The estimated value lies in `var('value_trusted_band')`, where the model held to ~1.5x in
validation; NULL for a stated value.
Synonyms: `value_in_trusted_band`.
{% enddocs %}

{% docs n_value_estimated %}
How many of the players summed into `value` have only an estimate.
Synonyms: `n_value_est`.
{% enddocs %}

{% docs n_owned %}
The players we own in our squad on the snapshot (those on loan to us not counted; those out on
loan counted).
{% enddocs %}

{% docs n_loan_in %}
The players on loan to us in our squad on the snapshot.
{% enddocs %}

{% docs contract_status %}
Where his contract stands on the snapshot: `contracted` (expiry on or after the snapshot),
`expired` (expiry passed, still at a club), `free_agent` (no club); NULL where a club holds him
with no expiry.
{% enddocs %}

{% docs is_contracted %}
The training row's contract flag (`var('contracted')`): the row says he is under contract.
{% enddocs %}

{% docs unknown_39 %}
Unverified: the training row's unnamed byte at +39, where the row says he is under contract. It
is not the squad status and not a loan flag (docs/parser/training.md); it changes under one
contract, so it is not a contract term.
{% enddocs %}

{% docs training_intensity %}
Training intensity: 3 high, 2 normal (the Training list); 1 and 0 also occur, unnamed.
{% enddocs %}

{% docs training_focus_role %}
The Focus Role he trains in, a `role_id`.
{% enddocs %}

{% docs training_focus_attribute %}
The attribute he trains, as the game codes it (`seeds/training_attributes.csv`).
{% enddocs %}

{% docs training_focus_position %}
The position he trains at, a position code.
{% enddocs %}

{% docs position %}
A position code, one of the fifteen in `dim_position` (`GK`, `DL`, `DC`, ..., `ST`). On a match
line, a starter's full-time place in his side's XI (NULL for a substitute).
{% enddocs %}

{% docs unit %}
The position's unit: `goalkeeper`, `defence`, `midfield` or `attack`.
{% enddocs %}

{% docs display_order %}
The order positions are listed in, back to front.
{% enddocs %}

{% docs familiarity %}
How familiar he is with a position, 1-20 (20 natural); 0 or no entry where he can't play it.
Synonyms: `pos_*` → `familiarity_*`.
{% enddocs %}

{% docs positions %}
Each position he can play (familiarity above 0), by code: a list of `{position, familiarity,
level_league, level_global}`. The levels are his Level %ile there: the share of the players
listing the position whose ability is below his, among all of them (`level_global`) and among
those whose team is in his team's league (`level_league`), 0-100 to one decimal; NULL with no
ability. The only form in which ability leaves the store.
{% enddocs %}

{% docs level %}
His Level %ile at the position in that division: the share of the players listing the position
whose team is in the division and whose ability is below his, of the `n_players` others, 0-100
rounded to a whole number. NULL with no one to compare.
Synonyms: `lvl`.
{% enddocs %}

{% docs development %}
How far he is from his ceiling, as a word: the first band of `var('site_development_bands')`
whose share of his potential his ability reaches (`At his ceiling`, `Nearly there`,
`Developing`, `Lots to come`); NULL with no potential.
{% enddocs %}

{% docs is_b_list %}
He goes on the B-list: born after the new year the rules take the B-list age on
(`b_list_age_date`, a house rule).
Synonyms: `b_list`.
{% enddocs %}

{% docs is_home_grown_club %}
Trained at the club (a house rule): he came out of it (an academy product, or his origin club
is ours), or he has `var('home_grown_months')` months with us in his window.
Synonyms: `hg_club`.
{% enddocs %}

{% docs is_home_grown_association %}
Trained in our nation (a house rule): home-grown at the club, or his origin club is of our
nation, or he has the months at another club of it.
Synonyms: `hg_association`.
{% enddocs %}

{% docs home_grown_basis %}
Why he is home-grown at the club: `academy` (an academy product of ours), `youth-origin` (his
origin club is ours), `clock` (the months); NULL if he isn't.
Synonyms: `hg_basis`.
{% enddocs %}

{% docs months_club %}
His months with us inside his home-grown window, up to the snapshot (int.squad_training).
{% enddocs %}

{% docs months_to_go %}
The months he still lacks for `var('home_grown_months')`, to one decimal; NULL once he has them.
{% enddocs %}

{% docs is_window_open %}
His home-grown window (from the season he turns 15 to the end of the season he turns 22) has
not closed.
Synonyms: `window_open`.
{% enddocs %}

{% docs is_academy_product %}
His origin line is a youth side (`origin_youth_team_tid` is set).
Synonyms: `via_academy`.
{% enddocs %}

{% docs origin_club %}
The name of his origin club.
{% enddocs %}

{% docs origin_nation %}
The name of his origin club's nation.
{% enddocs %}

{% docs is_loan_in %}
He is on loan to the team: the team listing him belongs to a club other than the one that owns
the team on his record.
{% enddocs %}

{% docs loaned_to_club_tid %}
The club he is out on loan at, for a player of ours; NULL otherwise.
{% enddocs %}

{% docs record_team_tid %}
The team his own record names (whose books he is on), which a loan or a lapsed loan can make
differ from the squad listing him.
{% enddocs %}

{% docs record_club_tid %}
The club that owns `record_team_tid`.
{% enddocs %}
