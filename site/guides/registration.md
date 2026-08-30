# Guide — registering the squad

**The save does not model any of this.** FMM22 has no A-list, no B-list and no home-grown
requirement. This is a self-imposed restriction: the Danish Herre-DM registration rules
(`docs/danish-registration-rules.md` in the repo) applied to the squad, so that squad building
has the constraint a real Superliga manager works under.

Everything below is therefore DERIVED. Say so when you report on it — a player is "home grown
on our reading of the save", not "home grown" as a fact the game asserts.

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
  association flag falls back to origin for exactly this reason; the club flag does not.
- **Origin is not automatically training.** A first recorded season at 19 or later does not make
  the origin club a training club, and is not credited as one.
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
back to the save or the store. It is a plan, not a fact. **Suggest a legal squad** builds one:
B-list everyone eligible, A-list the rest by rating, then promote home-grown players from the
B-list until the minimums are met — weakest first, since a strong player plays either way and
the slot is better spent on one you would otherwise leave out.
