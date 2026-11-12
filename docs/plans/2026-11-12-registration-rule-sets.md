# Registration rule sets per career (handoff)

Status: **not started**. This closes `docs/TODO.md` Stats item 4 ("Squad registration is Danish
for every career"); delete that entry when this lands.

## Why
Squad registration is a house rule (`site/AGENTS.md`, "Squad registration is a HOUSE RULE"):
the game enforces none of it. Today the whole feature is Danish (Herre-DM A/B lists) and
`site.registration_rules` applies it to whichever club is managed, so Truro's Squad page shows
Danish A/B lists. Zac wants the **real registration rules of whatever league the managed club is
in**. The immediate need is to see Truro's squad counted against **League Two** while still in
the National League South, so the squad isn't built to 40 men and then cut on promotion.

Zac's working target, from the 8 August 2026 snapshot: 27 first-team players, 22 of them 21 or
over, 2 young loans in. Truro is already **at** League Two's 22 over-21s limit.

## The rules to encode (England)
Taken from 2024/25 sources. No 2025/26 handbook was found, so **verify** them before
relying on them, and write sources into `docs/english-registration-rules.md`, as the Danish doc
does:
- [FourFourTwo, EFL squad rules 2024/25](https://fourfourtwo.com/features/what-are-the-efl-squad-rules-for-202425-loanee-limits-home-grown-players-and-how-many-subs-are-allowed)
- [The Star, EFL loan rules](https://www.thestar.co.uk/sport/football/sheffield-wednesday/the-efl-loan-rules-sheffield-wednesday-must-follow-3326636)
- [National League rule changes, 2024](https://bullsnews.blogspot.com/2024/08/major-change-to-national-league-rules.html)
- [National League, loan limit](https://www.thenationalleague.org.uk/no-transfer-window-in-national-league-31421)

| league | squad list | home-grown on the list | under-21s | matchday | loans |
|---|---|---|---|---|---|
| National League North/South (step 2) | no cap | none | n/a | 11 + 5 subs | max 5 in a matchday squad (older source) |
| National League (step 1) | no cap | none | n/a | 11 + 7 subs | max 5 in a matchday squad |
| League One, League Two | **max 22 aged 21+** | **min 8** | unlimited, not on the list | 11 + 7; **min 7 home-grown** | **max 5 in the matchday 18** (4 if one is an emergency GK loan); max 4 from one club; one source says max 2 over 23 |
| Championship, Premier League | look up when needed | | | | |

- **Home-grown (England):** registered with a club affiliated to the **FA or the FAW** for 3
  seasons or 36 months before the 21st birthday, nationality irrelevant. So Welsh clubs count,
  e.g. Penybont, the origin of player tid 29649. There is no "trained at the club" tier
  (`hg_club_min = 0`).
- **Under-21 cut-off:** the EFL takes age on a fixed date per season. Find the real date. Today
  the B-list age is taken on the last new year (`u21_on`); make the date part of the rule set.

## Current shape (read these first)
- `fmstats/dbt_project.yml`: var `registration: {a_list_max: 25, hg_min: 8, hg_club_min: 4,
  hg_tiers: 2, b_list_under_age: 21, min_matchday_age: 16}`, plus `home_grown_window_ages:
  [15, 22]` and `home_grown_months: 36`.
- `fmstats/models/site/site_registration_rules.sql`: one row per snapshot, the managed club's
  league and tier (`site_leagues.tier` = `competitions.level + 1`), and the Danish numbers.
- `fmstats/models/site/site_registration.sql`: per player per snapshot, `b_list`, `hg_club`,
  `hg_association`, months, ETA. "Domestic" is a single `our_nation` (the managed club's nation).
- `scripts/export_data.py`, the `registration.json` block (~line 587). Its `note` text is
  Danish-specific.
- `site/js/registration.js` (A/B/Unregistered column, quota card, per-device plan in
  localStorage) and `site/js/regwindows.js` (plans saved per transfer window to R2).
- The pattern to copy for per-career config: `eligible_origin_clubs` in `careers.py` →
  `load_duckdb.py` `seed_eligible_origin_clubs` → `raw.eligible_origin_clubs` →
  `stg_eligible_origin_clubs`.
- Docs: `docs/danish-registration-rules.md`, `site/guides/registration.md`,
  `docs/agent-context/homegrown-derivation.md`.

## The plan
1. **Rule sets as a seed.** Add `seeds/registration_rules.csv`, one row per (rule_set, tier
   range). Columns, roughly:
   - `rule_set, tier_from, tier_to, league_label`
   - `list_max` (null = no cap) and `list_label`, e.g. "Squad list" / "A-list"
   - `free_label`, e.g. "Under-21s" / "B-list"; `free_under_age`; `free_age_on` (a cut-off
     rule: "new_year" or a month-day)
   - `hg_min`, `hg_club_min`, `hg_nations` (e.g. `England|Wales`, or empty = the managed
     club's nation); the home-grown window ages and months, if they differ by country
   - `matchday_hg_min`, `matchday_loan_max`, `matchday_loan_max_per_club`, `min_matchday_age`

   Move Denmark's current numbers in unchanged (tiers 1–2 with home-grown quotas, 3–4 without,
   as `hg_tiers: 2` does now). Then add England: steps 1–2 (no cap), League One and Two (the
   table above). Use the tiers **as the save numbers them**: check `site.leagues.tier` for
   comp 331 (National League South) and for League Two in a Truro store. Don't assume 6 and 4.
   Add a dbt test that a rule set's tier ranges don't overlap.
2. **Each career names its rule set** in `fmm.toml`: `registration = "england" | "denmark" |
   "none"`. Default `"denmark"`, so Frem is unchanged; Truro `"england"`. Wire it like
   `eligible_origin_clubs`: a `Career` field (`careers.py`), seeded into raw by `load_duckdb.py`
   on every load and `--refresh-only` (a one-row `raw.career_registration`, or a column on the
   career table `stg_career` reads), then a staging model. Add the key to `fmm.example.toml`.
3. **`site_registration_rules` picks the row** by (career's rule set, the managed league's
   tier) per snapshot, so promotion switches the rules with nothing for the user to do. Also
   emit **every tier's row for the career's rule set** (a second model or a flag column). The
   site needs the other tiers for the "Count as" picker (step 5). With `"none"`, emit nothing,
   and the site already hides the card when `rules` is null.
4. **`site_registration`, made generic:**
   - `b_list` becomes "free" (under the rule set's age on its cut-off date). Keep the export
     key name, or rename it in both the export and the JS together.
   - `hg_association` counts any club whose nation is in `hg_nations`, not just `our_nation`.
     That is the England-plus-Wales case.
   - The home-grown window and months come from the rule set if they differ per country.
     Check the English "before 21" window against `home_grown_window_ages: [15, 22]`.
5. **Site:**
   - `registration.js` takes its labels and quotas from the rules: "Squad list / Under-21s"
     for England, "A-list / B-list" for Denmark.
   - Add a **"Count as" picker** to the card: *Current league (<league>)* and each other
     tier's rule set, e.g. *League Two*, *League One*. It recounts the plan against the chosen
     rules. Remember the choice per device and per career in localStorage, wrapped in
     try/catch like the existing plan keys.
   - A tier with no list cap shows the counts (over-21s, home-grown, loans) with no limit, so
     the National League South view still reads "22 over-21s, 7 home-grown, 2 loans".
   - `export_data.py`: ship the extra tiers' rules in `registration.json`, and make the `note`
     text not Danish. No new export file, so `sw.js`'s `DATA` list is unchanged.
6. **Optional, later: matchday check.** `mart.fact_player_match` holds each matchday squad,
   unused subs included. A `site` model can flag past matches with more loanees than
   `matchday_loan_max`, or fewer home-grown than `matchday_hg_min`. It is separate from steps
   1–5; ship those first.
7. **Docs and tests:**
   - Write `docs/english-registration-rules.md`, with sources and the 2024/25 caveat.
   - Generalise `site/guides/registration.md` and the "Squad registration is a HOUSE RULE"
     section of `site/AGENTS.md`.
   - Add the per-career rule to `career-notes/truro.md`. It's gitignored, the user's own file;
     add one line naming the rule set and the 22-player target.
   - Delete TODO item 4.

## Checks before pushing
- Frem must be a **no-op**: export Frem before and after and run `scripts/diff_exports.py`.
  The only differences allowed are deliberate ones: new keys (labels, other tiers' rules) and
  the note text. Frem's counts and verdicts must not move.
- On a Truro store, after `load_duckdb.py --refresh-only`:
  `cd fmstats && FM_DUCKDB=../fm-truro.duckdb uv run dbt test --profiles-dir .`; and the same
  for Frem.
- `uv run python tests/run_tests.py`, `tests/test_boundary.py`, `tests/test_site_offline.py`.
- Preview the Squad page (`uv run python -m http.server -d site 8000`). Truro, set to "Count
  as League Two", should show about 22/22 over-21s on the 2026-08-08 snapshot. Frem should
  look exactly as before.
- Immersion: nothing here needs ability numbers. `check_immersion()` must still pass.
