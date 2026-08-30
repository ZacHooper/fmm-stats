# Home-grown status, and the youth-team tids that make it possible

**Status: SHIPPED (2026-08-30).** The Danish registration rules
([`docs/danish-registration-rules.md`](../danish-registration-rules.md)) are enforced as a house
rule — FMM22 models none of it. Data layer: the registration family in `fmparser/mart.py`
(`club_nations`, `youth_clubs`, `player_training`, `player_homegrown`, `registration_rules`,
`squad_registration`). UI: the **Registration** section of the web app. User-facing explanation:
[`site/guides/registration.md`](../../site/guides/registration.md).

## The finding that unlocked it: origin tids in the 64000–65534 band are ACADEMY teams

`staging.player_history.origin_club_tid` is the head of the career-history chain — the club a
player came out of. For most players it resolves to a real club. For roughly 388 tids per
snapshot it renders as `#65189` and matches nothing in `staging.clubs`.

**Those are not garbage.** The players sharing one of these tids are overwhelmingly at ONE club:

| youth tid | where its alumni actually are |
|---|---|
| 65064 | Liverpool 8, Liverpool Reserves 3, then four lower-league strays |
| 65104 | Chelsea 5, Chelsea Reserves 4, then five strays |
| 64896 | Bayern München II 9, Bayern München 1 |
| **65189** | **Boldklubben Frem — all 7, and all ours** |

Which is exactly the shape of a youth side: the cohort sits at the parent club, and the strays
are academy graduates who moved on. `mart.youth_clubs` recovers the mapping by majority vote over
where each cohort ended up, and ships `share` + `alumni` so a caller can refuse a weak one —
cohorts average 2.8 players and 143 of the 388 are singletons, where the "majority" is one man.

**65535 is 0xFFFF, the u16 "no origin" sentinel** (2,096 players), not a club. Excluded
explicitly; `validate_mart.py` asserts it never enters `youth_clubs`.

Reserve sides vote for their first team, or our own academy maps to "Frem Reserves" half the time.

## Club nations, without a hardcoded nation table

`mart.clubs.nation` comes from the club's LEAGUE, and the save parks its unplayable clubs in
league buckets with no name and no nation — cid 245 holds 82 obviously-Danish clubs (Dragør BK,
Nexø BK Bornholm, Silkeborg BK). Three of our own squad's origin clubs live there, so "was he
trained at a Danish club" was unanswerable for them.

`mart.club_nations` fixes it with a two-step vote and no hardcoded table:

1. Learn what each `nationality_id` MEANS by asking which nation's leagues its players play in
   — 138 → Denmark, 139 → England, 145 → Germany, 170 → Spain. (`fmparser/reference.py`'s
   `NATIONS` dict holds only Turkey, so there was nothing to look up.)
2. Give a nation-less league the modal nation of its own players. cid 245's 46 players vote 138
   → Denmark.

`nation_source` is `'league'` or `'inferred'` and `nation_confidence` ships alongside, so an
inferred nation is never mistaken for a read one. 1,354 clubs get a nation this way.

## The 36-month clock

The rulebook test is 36 months registered at the club, between the start of the season he turns
15 and the end of the season he turns 21 (TR §14.1). `season_of` already knows a campaign runs
Jul–Jun and is named for its end year, so both window bounds are one macro call.

Two sources, unioned as DATED INTERVALS and merged (gaps-and-islands) before any month is
counted — adding two month-counts would double-count every season we both watched and read:

- **`mart.player_career_seasons`** — one row per season per club. A season with several legs (a
  mid-season loan) splits the Jul–Jun span evenly across its legs in `seq` order. An
  approximation, because the save stores no transfer date, and better than the alternative of
  crediting each leg a full season (24 months for one year of football).
- **`mart.at_club_spells`** — what we observed across the snapshots. It earns its place: at the
  2024-11-10 snapshot Johan Nordberg had no 24/25 history row at all despite being at the club
  since 2022, so history alone under-read him by a season. **Keyed on `person_id`, never `tid`** —
  tid 3505 was Mark Reynolds at Vejgaard before it was Johan Maarup here, and a tid-keyed join
  would credit one man's years to another.

A loan leg credits the HOST, not the parent (TR §15.2 — flagged as an inference in the rules
doc). That is the reading that costs us months rather than granting them: Adelgaard's 23/24 loan
to Frederiksberg is six months he does not accrue with us.

## Two deliberate departures from a literal reading

**Our academy counts outright** (manager's call, 2026-08). FMM only creates an intake player at
~16, so a strict clock calls a player our own academy produced *not* home grown until he is 19 —
backwards from the rule, where his youth registration already counts. `hg_club_basis` records
which route fired (`academy` / `youth-origin` / `clock`) and `months_club` ships regardless, so
the strict reading is one predicate away.

**An origin club is not automatically a training club — FOR THE CLUB FLAG.** Taken at face value,
`origin_club_tid` made Christian Bramsborg club-trained on the strength of a first Frem season at
19 with 21 apps, which says where he signed, not that he clocked 36 months there. So for
`hg_club`, origin counts only when it is an academy tid, OR his first recorded season starts at 18
or younger, OR his history begins *after* the window closed (the head row then predates everything
we can read, so it is the only view of his youth that exists — this is what saves the
34-year-olds, whose clock can only ever read zero).

**`hg_association` deliberately does NOT carry that gate** (fixed 2026-08-30; gating both was a
bug). The origin row is the club he was at BEFORE his first recorded season, so for a record
starting at 19 it covers ages 18 and under — squarely inside the window. That is enough to say he
trained at a club of this association; it is only "36 months at ONE club" that it cannot support.
Gating both read Bramsborg and Oliver Møller-Jensen — Danish, origin club *us* — as not home grown
at all, which is plainly wrong. Widening it takes our squad from 38/40 to 40/40 while leaving the
flag selective world-wide: 1,772 of 23,598 players, 67% of those at Danish clubs (not 100% —
imports exist), and 12 of the 6,432 at English clubs.

Watch the age arithmetic: `DATE_DIFF('year', dob, d)` is the difference of year PARTS, not
completed age, and reads 18 for an autumn-born 17-year-old. The mart subtracts the
birthday-not-yet-reached term, the same way `mart.player_snapshots` does.

## What it says about the current squad (2025 / 2024-11-10, Superliga tier 1)

40 in the squad · **11 club-trained** · 40 association-trained · 21 B-list eligible. Rules: 25-man
A-list, 8 home grown of whom 4 club-trained.

The binding constraints are the cap and the club-trained 4 — the association half is nearly free,
because the capital-region signing rule already means almost everyone was trained in Denmark.
World-wide the flags are properly selective: 1,772 of 23,598 players are Danish-association
home grown and 20 are club-trained by us.

**The interesting tension, and the reason the picker is not a checklist:** the B-list is free, so
the obvious move is to park every U21 on it — but the home-grown minimums are counted on the
A-LIST, and most home-grown players are young. Leaving club-trained Frederik Balslev (21) on the
B-list drops us to 3 club-trained, one short, and shrinks the A-list to 24.

**Two borderline cases worth knowing about:** Andreas Garly and Adam Jakobsen both sit on 35.9
months — 0.1 short — and Garly's window has already closed, so he misses club-trained status
permanently by less than the even-split approximation's own error bar. If a call like that ever
matters, read `mart.player_training` for the club-by-club months before treating it as settled.
