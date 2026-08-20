# Handoff — continue exactly where we are

Paste-ready context for a fresh agent. **Last updated 2026-08-21.**

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

## Phase 2 — NEXT UP, not started

A **static site on Cloudflare Pages** replaces hosting the dashboard. The user reads the data on
their phone and needing a laptop awake is the pain point; they also want Claude able to pull a
scout report from the phone with both laptops off. Streamlit stays local for interactive work.

**New `scripts/build_site.py`** renders into a committed `site/` dir, calling existing
`dashboard/db.py` functions so no analysis logic is duplicated:

- **`site/*.html`** — for the user. Squad overview, the position review (depth charts with Fam and
  ability ranks), league tables, last-match stats. Self-contained HTML, inline CSS, wide tables in
  `overflow-x: auto` containers so they behave on a phone.
- **`site/api/*.json`** — for Claude. `api/index.json` (snapshots, clubs, leagues),
  `api/club/<tid>.json` per club in the managed divisions (~48 files: position, familiarity,
  effective rating, fit + level percentiles, ability ranks, attributes), `api/squad.json` (ours,
  with contract/wage and last-season match stats). Scoped per club deliberately — the whole
  effective table is 30k players and hopeless in a chat context, but our squad plus one opponent
  is a few hundred KB.
- **IMMERSION RULE, actively guard it:** published JSON must carry `level_*` percentiles and
  ability *ranks* only, never raw `ca`/`pa`. Reusing `effective_table` (which `EXCLUDE`s `ca`) and
  `ability_rank_leagues/clubs` (which return only rank/N) preserves this by construction; a
  hand-rolled query is how it would break. Verify with `grep -ri '"ca"' site/api/`.
- **Deploy:** commit `site/`, let Cloudflare Pages' GitHub integration build on push. No wrangler,
  no Node toolchain. Refresh = import → `build_site.py` → commit → push.
- **`site/functions/api/shortlist.ts`** — a Pages Function with a native R2 binding (no
  credentials needed) accepting a POST from a small form on the site and PUTting one object to
  `state/shortlist/<id>.json`. Guard with a shared-secret header. This is why the shortlist moved
  to one-object-per-entry.

Deferred deliberately: **store dedupe** (`player_history_seasons` is 14% unique,
`player_positions` 9% — both re-stored per snapshot; would take the store 80 MB → ~30 MB) and a
hosted interactive Streamlit as a fallback if static proves limiting.

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
- **Loans out:** Karlsen (18, RB) → 2. Division, first choice at 4 clubs, £31.7k/wk idle — the
  standout. Dedes (20, LB) → 3. Division (Slagelse/Frederiksberg/Næsby). Pingel → Brabrand is a
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
