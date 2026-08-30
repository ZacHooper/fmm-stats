# Guide — registering the squad

**The save does not model any of this.** FMM22 has no A-list, no B-list and no home-grown
requirement. This is a self-imposed restriction: the Danish Herre-DM registration rules
(`docs/danish-registration-rules.md` in the repo) applied to the squad, so that squad building
has the constraint a real Superliga manager works under.

Everything below is therefore DERIVED. Say so when you report on it — a player is "home grown
on our reading of the save", not "home grown" as a fact the game asserts.

## Vocabulary — read this first

**"Home grown" is an umbrella term, not "trained at our club".** It is easy to read it the other
way and the rulebook does not help, so, in this app's words:

| term | means | counts toward |
|---|---|---|
| **Club-trained** ("Us") | 36 months at **our** club in his age-15-to-21 window | the 4 **and** the 8 |
| **Association-trained** ("Denmark") | the same, at **another Danish** club | the 8 only |
| **Home grown** | either of the above | the 8 |

So the 8 is the loose test almost every Dane passes, and the **4 club-trained** is the one that
bites. The squad table's `Trained at` column answers "where", the summary tiles answer "does the
A-list meet the quotas".

## The rules being enforced

| | |
|---|---|
| **A-list** | 25 players max. Changeable only in the two transfer windows. |
| **Home grown** | Tiers 1–2 only: 8 on the A-list, **of whom at least 4 trained at the club itself**; the remaining up to 4 trained at another club of the association. Tiers 3–4: no requirement. |
| **Penalty** | The A-list shrinks by the number of missing home-grown players. Six home grown means a 23-man A-list. No fine, no points deduction. |
| **B-list** | Unlimited, for players **under 21 at the last new year before the tournament year** — a fixed date, so a player who turns 21 in the autumn keeps his B-list place all season. Does not touch the A-list cap. |
| **Unregistered** | Cannot play. Fielding one is normally a forfeit if the team won or drew. |

The credit maths is not "count the home-grown players": with 3 club-trained and 5
association-trained the A-list is credited **7**, not 8, because only 4 non-club-trained places
exist. That is why the club-trained column matters more than the total.

**The A-list cap is always 25.** A home-grown shortfall does not change the cap; it reduces how
many of the 25 you are allowed to use, which the app shows as `A-list · 24 allowed` beside a
`24 / 25` count rather than by moving the denominator.

## Which is the binding constraint

For this career, the association half is nearly free — the capital-region signing rule means
almost every player was trained in Denmark. The constraints that actually bite are the
**25-man cap** and the **4 club-trained**.

## Where home-grown status comes from

The rulebook test is "eligible to play at the club for 36 months in total, between the start of
the season he turns 15 and the end of the season he turns 21". Three things in the save carry
that, and the mart (`fmparser/mart.py`, the registration family) combines them:

1. **Origin club** — the head of the career-history chain, i.e. the club he came out of. For an
   academy product this is a **youth-team tid** in the ~64000–65534 band that appears in no club
   table; `mart.youth_clubs` maps it back by asking where each cohort's alumni actually play
   (65189 → us, 65064 → Liverpool, 65104 → Chelsea). 65535 is the "none" sentinel, not a club.
2. **Career history** — one row per season per club, turned into dated Jul–Jun intervals. A
   season with several clubs is split evenly across its legs, because the save stores no
   transfer date.
3. **Our own snapshots** — the spells we watched happen, which fill the gap where the career
   history has not written the in-progress season yet.

Sources 2 and 3 are merged as intervals before any month is counted, so a season we both watched
and read is not counted twice.

**Two deliberate departures from a literal reading, both in the app's favour of being usable:**

- **Our academy counts outright.** FMM only creates an intake player at ~16, so a strict clock
  would call a player our own academy produced *not* home grown until he is 19. Origin = our
  academy is taken as club-trained; the 36-month clock is what SIGNED players earn it on.
  `hg_basis` says which fired (`academy` / `youth-origin` / `clock`), and `months_club` ships
  regardless, so the strict reading is one filter away.
- **A loan leg credits the host, not the parent.** That follows TR §15.2 and is flagged as an
  inference in the rules doc, not as a sourced rule. It is also the conservative reading — it
  costs us months rather than granting them.

## Where the evidence is thin

- **Older players.** The history slab does not reach back far enough to cover a 30-year-old's
  age-15-to-21 window, so his clock reads zero and only his origin club says anything. The
  association flag falls back to origin for exactly this reason; the club flag does not, so a
  long-serving veteran reads Danish-trained but not club-trained however long he has been here.
- **Origin proves the club, not the 36 months.** The origin row is the club he was at *before* his
  first recorded season, so for a player whose record starts at 19 it covers ages 18 and under —
  good enough to say he trained at a club of this association, not good enough to say he clocked
  36 months at one. So the association flag accepts a Danish origin outright, while the club flag
  still needs an academy tid, a first season at 18 or younger, or the clock.
- **Nation for exotic clubs is a guess.** A club in a league the save gives no nation to gets one
  from its players' modal nationality, which lands some non-league foreign sides in the wrong
  country (Kaizer Chiefs reads as England). It does not affect the Danish question — a club being
  called English rather than South African changes nothing here — but do not read `origin_nation`
  as authoritative for a club outside the playable leagues.
- **Borderline months.** The even split across a multi-club season is an approximation, so a
  player sitting a month either side of 36 could fall either way. Check `months_club` before
  treating a near-miss as settled.

## Reading it over the API

`api/registration.json` — `rules` (the tier's rule set, plus the `u21_on` date) and `players`,
positional rows named by `fields`:

```
tid, age, b_list, hg_club, hg_basis, hg_association, months_club, months_to_go,
hg_eta, window_open, origin_club, origin_nation, via_academy
```

Over SQL (the R2 mart copy — see AGENTS.md), the same thing plus the evidence:

```sql
USE m;                                  -- macros do not resolve across an ATTACH
SELECT name, age, b_list_eligible, hg_club, hg_club_basis, hg_association,
       months_club, months_to_hg_club, hg_club_eta
FROM mart.squad_registration
ORDER BY hg_club DESC, months_club DESC;

SELECT * FROM mart.registration_rules;              -- which rule set applies to our tier
SELECT * FROM mart.player_training WHERE tid = ?;   -- the months, club by club
```

`mart.player_homegrown` covers every player in the save, not just ours — so a recruitment target
can be checked for what he would add to the quotas before you sign him.

## The plan itself

The A/B assignment lives in the browser (localStorage, keyed by snapshot) and is never written
back to the save or the store. It is a plan, not a fact.

**Suggest a squad** builds one. The A-list cannot hold everyone — this squad is 40, of whom 19 are
too old for the B-list, 5 are on loan to us, and the spine is another 19 at depth 2, so any two of
those groups already overflow 25. It is therefore a priority order, not a filter:

1. **Loan-ins.** A loan slot was spent to have him available; an unregistered loanee wastes it.
2. **The spine** — the best N at each position under the selected tactic, first choices before
   second choices. N is the `Top 1/2/3 per position` picker, default 2 (a starter and his cover).
3. **The home-grown top-up**, strongest first: the spine is already registered, so everyone still
   available is outside it and the slot should hold the best of them.
4. **Everyone else too old for the B-list** — not because they are better than the youth left
   over, but because registration is the only thing standing between them and being unable to play
   at all. A B-list-eligible player left off the A-list still plays.

Whoever misses out is reported as unregistered rather than quietly dropped: that is a real squad
decision (those are the players to sell or loan out), and the card says how many A-list places are
held by B-list-eligible players, since freeing one of those costs nothing.

At depth 2 this career lands on a legal 25 with every position's top two registered, all five
loan-ins on the A-list, and six surplus seniors left off. Depth 3 starts cutting useful seniors to
register third-choice youth, which is why 2 is the default rather than the maximum.
