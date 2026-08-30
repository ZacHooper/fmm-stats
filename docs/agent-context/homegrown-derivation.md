# Home-grown status, and the youth-team tids that make it possible

**Status: SHIPPED (2026-08-30).** The Danish registration rules
([`docs/danish-registration-rules.md`](../danish-registration-rules.md)) are enforced as a house
rule — FMM22 models none of it. Data layer: the registration family in `fmparser/mart.py`
(`club_nations`, `youth_clubs`, `player_training`, `player_homegrown`, `registration_rules`,
`squad_registration`). UI: the **Registration** section of the web app. User-facing explanation:
[`site/guides/registration.md`](../../site/guides/registration.md).

**Vocabulary, because it trips people up:** "home grown" is the UMBRELLA — `hg_club`
(trained at us, counts toward both the 4 and the 8) plus `hg_association` (trained at another
club of our association, counts toward the 8 only). `hg_club` implies `hg_association`, and
`validate_mart.py` asserts it. The site's column is called "Trained at" for this reason: naming
it "Home grown" read as a definition ("home grown = Danish") rather than as a quota.

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

**We run the upper bound one season longer — to the end of the season he turns 22, i.e. the last
season in which he is still 21** (manager's call, 2026-08). The literal text shuts a March-born
player's window the June he is 21 and three months old, while an autumn-born player in the same
position accrues another nine months purely on his birthday. Andreas Garly — four seasons at the
club, still 21 at the snapshot — closed out on 35.9 months and missed club-trained status
permanently by a tenth of a month, inside the error of the even-leg split. With the extra season
he reads 40.3 and qualifies on the clock.

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

## Three deliberate departures from a literal reading

(The first is the window's upper bound, above.)

**Our academy counts outright** (manager's call, 2026-08). FMM only creates an intake player at
~16, so a strict clock calls a player our own academy produced *not* home grown until he is 19 —
backwards from the rule, where his youth registration already counts. `hg_club_basis` records
which route fired (`academy` / `youth-origin` / `clock`) and `months_club` ships regardless, so
the strict reading is one predicate away.

**The origin club IS the youth club, so origin = us is club-trained outright.** No age test on
top of it — and a briefly-shipped version that added one was simply wrong. The theory behind the
gate was that a first Frem season at 19 says where a player SIGNED rather than where he trained,
so Christian Bramsborg and Oliver Møller-Jensen (origin: Boldklubben Frem, first recorded season
at 19) were denied. The data refutes it: **Mikkel Bruhn (34) and Daniel S. Jørgensen (33) both
have their first recorded season at 21, yet their origin clubs read Espergærde IF and Næstved BK**
— their real youth clubs, not whoever they played for at 21. The chain head is stored
independently of where the recorded seasons begin, which is precisely why a player signed from
elsewhere at 19 carries THAT club as his origin rather than us. An origin of us can only mean he
came out of us.

`age_at_first_season` is still carried as evidence for a human reading a borderline case, but
nothing branches on it. Two rounds of this: gating `hg_association` too was the first bug (fixed
the same day), which had those two reading as not home grown *at all*.

The flags stay selective world-wide: **1,772** of 23,598 players are association home grown (67%
of those at Danish clubs — not 100%, imports exist; 12 of the 6,432 at English clubs), and **24**
are club-trained by us.

Watch the age arithmetic: `DATE_DIFF('year', dob, d)` is the difference of year PARTS, not
completed age, and reads 18 for an autumn-born 17-year-old. The mart subtracts the
birthday-not-yet-reached term, the same way `mart.player_snapshots` does.

## What it says about the current squad (2025 / 2024-11-10, Superliga tier 1)

40 in the squad · **14 club-trained** · 40 association-trained · 21 B-list eligible. Rules: 25-man
A-list, 8 home grown of whom 4 club-trained.

The binding constraints are the cap and the club-trained 4 — the association half is nearly free,
because the capital-region signing rule already means almost everyone was trained in Denmark.
World-wide the flags are properly selective: 1,772 of 23,598 players are Danish-association
home grown and 24 are club-trained by us.

**The interesting tension, and the reason the picker is not a checklist:** the B-list is free, so
the obvious move is to park every U21 on it — but the home-grown minimums are counted on the
A-LIST, and most home-grown players are young. Leaving club-trained Frederik Balslev (21) on the
B-list drops us to 3 club-trained, one short, and shrinks the A-list to 24.

**Borderline months are still the thing to watch.** Garly's 35.9 is what forced the window
change above; Christian Bramsborg now sits on the same 35.9 and is club-trained by origin rather
than by the clock, so nothing turns on it. If a call like that ever
matters, read `mart.player_training` for the club-by-club months before treating it as settled.
