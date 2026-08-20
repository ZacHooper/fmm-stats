# Handoff — continue exactly where we are

Paste-ready context for a fresh agent. **Last updated 2026-08-21 (Phase 2 built).**

Read [`CLAUDE.md`](../CLAUDE.md) first, then
[`docs/agent-context/MEMORY.md`](agent-context/MEMORY.md) which indexes the durable notes. This
file is only *where we are right now* and *what's next*.

---

## The project in three lines

Reverse-engineering **Football Manager Mobile 2022** `.fms` saves into a DuckDB store + a
Streamlit dashboard, to manage a career with real data. The active career is **Boldklubben Frem**
(Denmark, `--career frem`, managed tid 346, reserves 7296). Bucaspor (Turkey) is archived: its
saves are kept as the only cross-career parser regression test, but its store isn't rebuilt.

---

## Storage architecture — Phase 1, DONE and verified (2026-08-20/21)

The project was reorganised so it can be worked from two laptops. **The DuckDB store is a build
output, not an artefact** — never committed, never synced, always rebuildable. Full reasoning in
[`agent-context/multi-device-and-storage.md`](agent-context/multi-device-and-storage.md); read
that before touching data layout.

| Tier | Holds | Where |
|---|---|---|
| Code + build inputs | source, `seeds/` (role_weights, eligible_origin_clubs, config_bundle, **manifest**) | git — **`github.com/ZacHooper/fmm-stats`** (public) |
| Archive + live state | `.fms.gz` saves, shortlist, saved scouts | Cloudflare R2 — **`r2:fmm-stats`** |
| Derived | `fm-frem.duckdb`, `output/`, `site/` | local only |

**Bootstrap on a new machine** — clone, `uv sync`, `rclone config` (S3-compatible → Cloudflare
R2, remote named `r2`), then:

```bash
uv run python scripts/rebuild.py --career frem      # fetches from R2, extracts, loads (~12 min)
```

**Verified end to end:** a full 12-snapshot rebuild matched the live store on 22 of 24 tables,
including every large one (`player_history_seasons` 2,524,465; `players` 362,980). The two
differences both favoured the rebuild — `league_members` had 28 fewer rows because rebuilding
propagated the club→league fix to all 12 snapshots instead of the 1 previously reloaded, and
`staging.shortlist` is gone because the shortlist now lives in `state/`. All 14 dashboard pages
pass, including against a read-only store.

### Naming convention (applied to all 19 snapshots)

**`<career>-<YYYY-MM-DD>[-<tag>].fms`**, and the **label is the same string** — so save file,
`output/` dir and `staging.extracts.label` are one vocabulary. The date is the save's *in-game*
date, which is exactly `phase`. New saves:
`scripts/archive_save.py <file> --career frem --phase <date> --upload`. The date can't be derived
from a 0-match save, so it's an argument — **ask the user for it**.

### Scripts added in Phase 1

| Script | Does |
|---|---|
| `scripts/rebuild.py` | the whole bootstrap: fetch → gunzip → extract → load, per manifest row |
| `scripts/export_manifest.py` | regenerate `seeds/manifest.csv` from the stores (run after any import) |
| `scripts/archive_save.py` | move a save into `$FM_SAVES_DIR`, gzip, hash-verify the round-trip, upload |
| `scripts/canonicalise_names.py` | retro-fit the naming convention across all 5 places a name appears |
| `scripts/migrate_state.py` | one-time: store shortlist/scouts JSONL → `state/` objects |
| `scripts/_dbopen.py` | open a store read-only, refusing to byte-copy one with a live writer |
| `dashboard/state.py` | `state/<kind>/<id>.json` mirrored to R2, one object per entry |

---

## Phase 2 — BUILT, waiting on a Cloudflare Pages project

A **static site** replaces hosting the dashboard: the user reads the data on a phone, and
needing a laptop awake was the pain point. Streamlit stays local for interactive work.
Deployment runbook: [`DEPLOY.md`](DEPLOY.md).

**`scripts/build_site.py`** renders everything in ~7s into a committed `site/` dir:

| Output | For | Notes |
|---|---|---|
| `site/index.html` | phone | priorities this window, weakest/strongest roles, the move-on list |
| `site/positions.html` | phone | the full depth charts + loan destinations (76 KB) |
| `site/squad.html` | phone | every owned player, **including** the 8 the depth charts exclude |
| `site/form.html` | phone | season-by-season, last 20 matches, last season's minutes |
| `site/divisions.html` | phone | all 3 ladder divisions ranked by squad index |
| `site/shortlist.html` | phone | the one page that WRITES — talks to the Pages Function |
| `site/api/index.json` | Claude | the manifest: snapshot, ladder, every file, the caveats |
| `site/api/squad.json` | Claude | 46 owned players, per-role reads, contracts, attributes |
| `site/api/positions.json` | Claude | the position review as data |
| `site/api/form.json` | Claude | 81 deduped matches |
| `site/api/club/<tid>.json` | Claude | 36 clubs across the 3 divisions, ~620 KB total |

**The analysis is not duplicated.** The depth-chart computation moved out of the Streamlit page
into **`dashboard/positions.py`**, which both the page and the build call — so the site is a
second *screen*, not a second *opinion*. `13_Positions.py` is now rendering only; verified the
extracted logic is semantically identical to what it replaced (the diff is line-wrapping and one
unused-variable rename).

**The immersion rule is enforced, not just intended.** `build_site.py` walks every emitted JSON
and fails the build on a raw-ability key at any depth (`ca`, `pa`, `current_ability`, …) — a
parse, not a grep, so `{"CA": …}` can't slip through and the word inside prose doesn't
false-positive. Currently passing.

**`functions/api/shortlist.ts`** — a Pages Function with a native R2 binding (no credentials).
GET lists, POST adds, DELETE removes, all gated by an `x-fm-token` header. It lives at the
**repo root**, not in `site/`, because `--clean` wipes the output dir. Verified end to end
against real R2: an object in the exact shape the Function PUTs was read back by
`dashboard/state.py` → `db.shortlist_get()`, the id stayed int-coercible (the Squad Tool casts
it), and `shortlist_remove()` deleted it again. The browser JS passes `node --check`.

**What's left is a dashboard click, not code:** create the Pages project (build command empty,
output dir `site`), bind `FM_STATE` → `fmm-stats`, set the `FM_SHORTLIST_TOKEN` secret. All of
it is in `DEPLOY.md`, including the cost to watch — ~800 KB committed per refresh, which
deltas poorly, and the `wrangler pages deploy` escape hatch if it starts to bite.

Deferred deliberately: **store dedupe** (`player_history_seasons` is 14% unique,
`player_positions` 9% — both re-stored per snapshot; would take the store 80 MB → ~30 MB) and a
hosted interactive Streamlit as a fallback if static proves limiting.

### Two things the build surfaced

- **`staging.standings` is not usable for this career** — a 22-game division parses back with
  max `played` 12, and the newest snapshot has no NordicBet Liga table at all. So there is no
  league table on the site; `divisions.html` ranks clubs by **squad index** instead, which
  answers the same question honestly. Note that index scores every club under *our* weight-set,
  so it reads as "how well their players fit the way we play", not raw quality.
- **A club with no rated players used to vanish silently.** `api/index.json` now lists them in
  `clubs_without_rated_players` — currently FC Sydvest 05 Tønder, which is exactly why 3.
  Division reads as 11 clubs on `effective_table` and 12 on `league_members`.

---

## Loose ends (all small, none blocking)

1. **The R2 token has not been rolled.** Its access key/secret were pasted into a chat transcript.
   Create a replacement in Cloudflare → R2 → Manage API Tokens, then
   `rclone config update r2 access_key_id <NEW> secret_access_key <NEW>`.
2. **4 saves are `unfiled/`** — real snapshots never loaded, so no in-game date and no canonical
   name: `frem/unfiled/denmark-mid-22.fms`, `bucaspor/unfiled/{22-23-start, fm_save1-24-mid,
   fm_save3}.fms`. If the user supplies their in-game dates they can be filed properly.
3. **~308 MB of stale `output/` dirs** from old experiments (`patched-test`, `multi-region-test`,
   `frem-22-start`, pre-rename leftovers). All regenerable; offered, not deleted.
4. **`~/fm-parser-git-backup-20260820.tar`** (302 MB) + `/tmp/oldgit` — the pre-history-rewrite
   backup. Safe to delete now the rebuild is verified.
5. **Streamlit is stopped** (had to be, for a store swap). Restart with
   `uv run streamlit run dashboard/Home.py`.
6. `docs/agent-context/fm-parser-project.md` and `day1-league-membership.md` cite commit SHAs
   (`aac6cbe`, `0b9a679`, `9c89633`, `d0f60af`) that the history rewrite invalidated. Cosmetic.
7. **The Pages project doesn't exist yet** — see `DEPLOY.md`. Until it does, preview with
   `uv run python -m http.server -d site 8000`.

---

## The other open thread — the football

Interrupted mid-flow by the infrastructure work; the user may want to resume it.

**Situation:** 2023/24 pre-season, snapshot `2024 / 2023-07-02`. Frem were promoted twice and are
now in the **NordicBet Liga (1. Division, tier 2)** — so the squad was built to win the 4th tier
and most of it is below the level. Tactic is **`frem_attacking_ss`** (strikerless SS), the
dashboard default.

**Delivered:** a new **Positions page** (`dashboard/pages/13_Positions.py`) — depth chart per role
with a keep/loan/sell read, a "where the window money goes" summary, and loan-destination lists.
Plus GK/LB/RB/CB written up in chat.

**Findings that shouldn't be relost:**
- **Transfer priority: LB (starter) > CB (starter) > AMR.** LB is the worst position in the squad —
  best specialist is 43/50 in the division at familiarity ≥15. CB has only two players you'd start
  and Jørgensen is 32.4 with one year left; below him every centre-back is a visitor (Fam 10–17),
  the only natural one being Frahm, who is the release candidate.
- **RB and AML also sit below par** by ability, but with 5 and 9 bodies they're lower priority.
- **AMC reads "prospect starting"** — Nordberg is 17, so his 109/113 ability rank is his age, not a
  verdict. Buy cover, not a replacement.
- **Against 4-1-2-2-1:** only **four** players have ST familiarity ≥15, and Nordberg at striker is
  64/70 in the division on Fam 15. Jakobsen is the one genuine striker (11/70 in our division,
  1/64 in the tier below) and already the focal point of the strikerless setup.
- **Loans out:** Karlsen (18, RB) → 2. Division, first choice at **6** clubs there and 9 in 3.
  Division, £31.7k/wk idle — the standout. (The "4 clubs" in an earlier draft of this file
  didn't survive recomputation; the shared builder at Fam ≥15 says 6.) Dedes (20, LB) → 3. Division (Slagelse/Frederiksberg/Næsby). Pingel → Brabrand is a
  tidy exit, not development: he'd be 9/9, 15/15 and 10/10 at their three positions.
- **Releases:** Rwango (last of 88 in the division, starts nowhere below us), Basarte, Dirksen,
  Frahm. **Sell:** Youssef (ability-identical to Fredslund, four years older than Bramsborg who
  costs half as much, expiring anyway).
- **GK:** Ullits (19) is already the best of the three by ability and played zero minutes. Bruhn's
  contract ends June 2024 — give Ullits real minutes now rather than handing him a debut and the
  No.1 job simultaneously next summer.

**The user's outstanding ask:** the same position-by-position write-up for **DM, CM, AML, AMC, AMR
and ST**, plus a verdict on the 4-1-2-2-1 question.

**House rules to honour:** never surface raw CA/PA (percentiles and ranks only — the Positions page
and the `ability_rank_*` helpers are built to make this structural); opponent tactics/formation are
NOT in the save, so always ask for the in-game scout's formation + style; the user's self-imposed
**capital-province rule** (new signings must have a Region Hovedstaden origin club — existing squad
and academy products are grandfathered; the allow-list is `seeds/eligible_origin_clubs.csv`).
