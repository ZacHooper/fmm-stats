# Guide: scout an opponent

You are the technical analyst briefing the manager before a match. Read
[`../AGENTS.md`](../AGENTS.md) first if you haven't — this guide assumes you can compute a role
rating and know the immersion rule.

## Before you pull anything: ask

**Opponent formation and playing style are NOT in the save file.** They cannot be derived from
anything here. Ask the manager for the in-game scout's report:

> What formation and style is the in-game scout showing for them? And is it home or away?

Do not proceed to a game plan without it. A briefing that guesses their shape is worse than no
briefing, because it reads as authoritative. You *can* do the squad-profile half while you wait —
say which half is provisional.

## Fetch

1. `api/index.json` — career, snapshot, `ladder`, caveats.
2. `api/core.json` — attributes, tactics, clubs, leagues.
3. `api/matches.json` — for head-to-head.

Resolve the opponent: find them in `core.clubs` by name. **Watch for a same-named reserve side** —
take the one with the larger squad. If they aren't in `core.clubs` at all they're outside the
division ladder; fetch `/api/all` and note that you have attributes but no division context.

## The report

Use the manager's default method (`index.snapshot.default_method`) unless asked otherwise.

### 1. Head-to-head
Filter `matches.matches` on `opp_tid`; drop friendlies. Report P / W-D-L / GF-GA / points per game,
then look at the per-match team stats for the *pattern*, not just the result:

- `our_shots` vs `our_shots_on_target` — plenty of shots and none on target is a **penetration and
  finishing** story, not a control one. Say which.
- `our_passes_completed / our_passes` vs theirs — who had the ball, and did it matter.
- `our_tackles_won`, `our_interceptions` — where the game was actually contested.

One or two meetings is an anecdote. Say so rather than dressing it as a trend.

### 2. Squad profile, unit by unit
For both clubs, take each player's **best role** under the method, assign him to a unit
(GK / Defence / Midfield / Attack from his position), and take the best XI per unit
(1 GK, 4 defenders, 3 midfielders, 3 attackers by rating). Compare per-unit means using the
**position index** (standardise rating within position: 100 = pool mean, 15 = one s.d.) —
raw ratings are not comparable across positions.

Then compare **attribute means** per unit. The biggest gaps are the story: pace, aerial ability,
strength, creativity, decisions. State the mismatch, not the table.

### 3. Their danger men
Rank their squad by position index. For each of the top few, give the position, familiarity, the
ability percentile (`lvl_league`), and his standout attributes — the highest values among those
the tactic weights ≥2 for his role. Look for the shape of the threat:

- one standout with a steep drop to the next man → mark him out of the game
- an evenly good unit → a positional problem, not a man-marking one
- a centre-back with high Aerial and Strength → a set-piece threat both ways

### 4. Their weaknesses
Same data, inverted. Low `lvl_league` at a position they must field is where to attack. Low
Pace across their back line invites balls in behind; low Aerial invites crosses and set pieces;
low Decisions and Positioning invite pressing their build-up.

### 5. Level check
Compare best-XI mean position index for both clubs. Are we favourites, evens, or underdogs — and
by how much? This decides the whole plan, so state it plainly before recommending anything.

### 6. Game plan and tactic recommendation
Combine the manager's scout report with what you found. Recommend **one base method plus the lever
to pull if the game turns**. Available methods are in `core.tactics`; for this career the shape is:

- **`frem_attacking_ss`** — the default. Proactive; use when we're better or even.
- **`frem_counter`** — when they're stronger, or when they carry pace we can hit in behind.
- **`frem_lowblock_overload`** — when they'll sit in a deep block and we have to break them down.
- **`frem_gegenpress`** — when they'll try to play out from the back and their build-up is weak.
- **`frem_game_state`** — closing out a lead.

Two rules worth honouring: don't open in a high-press duel game against a side that edges us
physically and plays direct — that plays to their one advantage. And if the level gap is large in
our favour, the risk is complacency and a low block, not their attack.

You can test a switch: recompute ratings under a different method and see whether it actually
improves our best XI at the positions that matter. Don't recommend a switch you haven't checked.

## Output shape

Keep it to what a manager reads before a match:

1. **The line** — one sentence: who's better, by how much, and the single thing that decides it.
2. **Head-to-head** — record plus the pattern.
3. **Their threat** — named players, what they do, who handles it.
4. **Their weakness** — where we attack, concretely.
5. **Recommended method** — plus the in-game switch if it turns.
6. **What you're unsure about** — including anything that depended on the scout report, and
   anything the caveats in `index.json` undermine.

Use real names — every club's players are resolved. Percentiles, ranks and attributes only; never
a single ability score. Their attribute values are estimates (±1) outside pace and physicals, so
don't build an argument on one point of difference.
