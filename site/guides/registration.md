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
| **Club-trained** ("Us") | the save names us as the club he came out of, or 36 months with us inside his eligibility window | the 4 **and** the 8 |
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
the season he turns 15 and the end of the season he turns 21". **We run the window one season
longer, to the end of the last season in which he is still 21** — see the departures below.
Three things in the save carry the months, and the mart (`fmstats/mart.py`, the registration
family) combines them:

1. **Origin club** — the head of the career-history chain, i.e. the club he came out of. For an
   academy product this is a **youth-team tid** that appears in no club table. It is the u16
   complement of the club's own tid, so `mart.youth_clubs` maps it back exactly — `65535 - tid`,
   no guessing (65189 → us, 65064 → Liverpool, 65104 → Chelsea). 65535 is the complement of tid 0,
   i.e. the "none" sentinel, not a club.
2. **Career history** — one row per season per club, turned into dated Jul–Jun intervals. A
   season with several clubs is split evenly across its legs, because the save stores no
   transfer date.
3. **Our own snapshots** — the spells we watched happen, which fill the gap where the career
   history has not written the in-progress season yet.

Sources 2 and 3 are merged as intervals before any month is counted, so a season we both watched
and read is not counted twice.

**Three deliberate departures from a literal reading, all in the app's favour of being usable:**

- **The window runs to the end of the season he turns 22**, not the season he turns 21. Taken
  literally, a March-born player's window shuts the June he is 21 and three months old, while an
  autumn-born player in the same position keeps accruing for another nine months purely on his
  birthday. Andreas Garly — four seasons at the club, still 21 — closed out on 35.9 months and
  missed club-trained status permanently by a tenth of a month, which is inside the error of the
  even-leg split above. The extra season gives everyone his full seventh year and takes the
  birthday lottery out of the borderline cases.

- **Coming out of our club counts outright.** If the save says a player's origin club is us — our
  academy side or the club itself — he is club-trained, with no 36-month test on top. The origin
  club is the head of his career-history chain and is stored independently of when his recorded
  seasons start, so a player signed from elsewhere at 19 carries THAT club as his origin, not us.
  (Mikkel Bruhn's first recorded season is at 21 and his origin still reads Espergærde IF.) The
  clock is what players signed from elsewhere earn club-trained status on. `hg_basis` says which
  route fired (`academy` / `youth-origin` / `clock`) and `months_club` ships regardless, so a
  stricter reading is one filter away.
- **A loan leg credits the host, not the parent.** That follows TR §15.2 and is flagged as an
  inference in the rules doc, not as a sourced rule. It is also the conservative reading — it
  costs us months rather than granting them.

## Where the evidence is thin

- **Older players.** The history slab does not reach back far enough to cover a 30-year-old's
  eligibility window, so his clock reads zero and only his origin club says anything. The
  association flag falls back to origin for exactly this reason; the club flag does not, so a
  long-serving veteran reads Danish-trained but not club-trained however long he has been here.
- **Origin is a club, not a duration.** It says where he was trained, never for how long, so it
  can settle "trained at us" and "trained in Denmark" but never a borderline 36-month question for
  a player who came from somewhere else. For those, read `months_club`.
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

**Saved windows.** `Save window…` keeps the lists as they stand as the registration for one
transfer window (`Summer 2027`, `Winter 2028`) — one record per window, so saving the same window
again replaces it. With the device token (the shortlist's) it goes to R2 at
`state/registrations/<year>-<summer|winter>.json` and every device sees it; without one it stays
in this browser. Each record carries the players' names, positions, ages and home-grown status
as they were, so a window reads correctly after its players have left. Opening one shows the three
lists and what has changed since — who left, who is new, who has aged out of the B-list — and
**Load into plan** makes it the starting point for the next window: players still here keep their
list, new players get the default, and a B-lister now too old is flagged as unregistered for you
to place.

**Where it lives.** Registration is part of the **Squad** page, not a section of its own. The
**List** column (Registration preset) holds each player's A / B / — toggle and filters like any
other column; the **Squad** card at the top carries the squad size, is coloured by the worst rule
breach (red over the cap, amber for a home-grown shortfall or anyone unregistered), and opens the
full breakdown on hover or tap; saved windows sit under the table. A snapshot with no plan of its
own starts from the newest plan the browser holds for an earlier snapshot — players still here
keep their list, a B-lister who has aged out becomes unregistered, a new arrival goes to the
B-list if eligible and is otherwise unregistered. With no earlier plan at all, B-list-eligible
players start on the B-list and everyone else on the A-list.

Whoever misses out is reported as unregistered rather than quietly dropped: that is a real squad
decision (those are the players to sell or loan out), and the card says how many A-list places are
held by B-list-eligible players, since freeing one of those costs nothing.
