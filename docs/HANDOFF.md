# Handoff — continue exactly where we are

Paste-ready context for a fresh agent. **Last updated 2026-08-24 (Phase 3: direct-R2 SQL access
verified end-to-end; real store upload + PR checklist still pending).**

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

## Phase 2 — the web app. **LIVE** at <https://fmm-stats.zac-g-hooper.workers.dev>

**One app for phone and desktop**, replacing the idea of a reduced "phone view". The first pass
pre-rendered six HTML pages; that was wrong — a finished table can't be searched, re-columned or
sorted, so it was a screenshot rather than a tool. It's now a static single-page app that ships
DATA and computes on the client. Runbook: [`DEPLOY.md`](DEPLOY.md).

### The architecture decision that makes it work

**Ratings are computed in the browser.** A role rating is `SUM(attribute × weight)` and the whole
weight table is 5 KB, so the app ships attributes + weights instead of precomputed ratings —
smaller than shipping ratings for 7 tactics, and strictly more capable: switching tactic re-rates
every player instantly with no rebuild. **Verified against the database: 36,920 (player, tactic,
role) combinations and 3,302 effective ratings, zero difference.** That test lives in the
scratchpad; it's worth recreating if the engine is touched.

**Ability percentiles are NOT computed in the browser** — they derive from the ability number,
which never leaves the build machine. `Level %ile` ships precomputed and is the only ability that
exists client-side. `export_data.py` parses every file it writes and fails on a raw-ability key at
any depth.

**The 4 MB every-player file is not in git** — it rewrites wholesale each import and minified JSON
deltas badly (the DuckDB-store mistake again). It lives in R2 at `site-data/all.json` and is
streamed by `functions/api/all.ts`; only a global search pays for it. Everything committed is
125 KB gzipped.

### Sections (13 dashboard pages collated into 6)

| Section | Collates | Notes |
|---|---|---|
| **Squad** | squad list + Development + Player Stats + attributes | ONE table: identity, fit, level, growth Δ + sparkline, contract, any of 23 attributes, any match stat — all add/remove from one picker with presets. Search, sort, unit filter, multi-select → Compare |
| **Positions** | Positions | the depth charts; the only view computed server-side (ability ranks need the ability number), so it's pinned to the exported tactic and says so |
| **Recruitment** | Squad Tool shortlist + Recruitment + player search | searches all 23,799 players (lazy R2 fetch), the capital-region rule, and the shortlist (the only thing that WRITES) |
| **Opposition** | Team scout + Divisions + League Rankings | pick a club → unit-by-unit edge vs us + danger men; divisions by squad index; reputation ladder |
| **Matches** | Matches + Player Stats | results, H2H, per-competition, team differentials, formations, and a re-aggregating player grid — all filtered together |
| **History** | Records + Awards | season progression, team + player records, longest runs, and a 10-award roll per season |

Shared: a **player profile sheet** (attributes coloured by the selected tactic's weights for that
role, growth sparkline, match record, career history) and a **compare sheet** (radar over the
weighted attributes + attribute-by-attribute diff), reachable from every table.

### Files

| File | Role |
|---|---|
| `scripts/export_data.py` | the exporter — 6 JSON files, ~5s, with the immersion check |
| `site/index.html`, `site/app.css` | the shell (hash routing, mobile-first, dark/light) |
| `site/js/data.js` | loading + the rating engine + match aggregation + stat vocabulary |
| `site/js/table.js` | the configurable table (search / sort / column picker / presets) |
| `site/js/profile.js` | the player profile + compare sheets |
| `site/js/app.js` | router, tactic + snapshot selectors |
| `site/js/views/*.js` | the six sections |
| `functions/api/all.ts` | streams the every-player file from R2 |
| `functions/api/shortlist.ts` | shortlist GET/POST/DELETE against R2, token-gated |
| `dashboard/positions.py` | depth-chart logic shared by Streamlit and the exporter |

### Two bugs the build surfaced, both fixed

- **Growth trends were blank for every new signing.** The trajectory query filtered on
  `club_tid IN OUR_CLUBS`, so a summer arrival had no history — yet his attributes are in every
  snapshot, he was just at another club. Widened to the whole file, which then crosses **tid
  recycling**: `db.keep_current_person` drops the slices where a tid belonged to someone else. It
  fires on real data (6 rows), so without it two people's growth would be spliced into one line.
  46 of 46 players now have a trend, up from 26.
- **`ours.origin` shipped all 23,799 players' origin clubs** (556 KB) in a file loaded on every
  page view, where only our squad is ever asked for.

### What is still dashboard-only, deliberately

**Tactics** and **Config** write to DuckDB, so they can't move to a static app — edit them in
Streamlit (or `seeds/`) and re-export. **Team Builder** could be ported (attributes and weights
are both client-side already) but isn't yet: it's a view to write, not a data problem.

### Deployed as a WORKER, not Pages

Worth knowing before touching the deploy: it runs as a **Cloudflare Worker with static assets**
(`*.workers.dev`), so a Pages `functions/` directory is **not read** — both endpoints 404'd with an
empty body until the logic moved to `worker/index.js`. (An empty-bodied 404 is the tell: the
endpoints return JSON even when they fail, so a bodyless 404 is the asset handler, not the code.)
`wrangler.jsonc` is the source of truth for the entrypoint, assets dir and R2 binding.

**Verified on the live host:** static assets, `AGENTS.md`, `guides/scout.md`, `/api/all` (200,
4,330,533 bytes streamed from R2, ETag→304 on repeat), `/api/shortlist` (401 failing closed).
4.63 MB of deployed JSON re-checked for raw ability: **none**, with 3,302/3,302 level percentiles
and 92/176 league skill indices present.

**The only step left is `FM_SHORTLIST_TOKEN`** — a secret, so deliberately not in the repo:
`npx wrangler secret put FM_SHORTLIST_TOKEN`, then paste the same value once per device under
Recruitment → Shortlist. Until then the shortlist is read-only-and-closed by design.

Deferred: **store dedupe** (`player_history_seasons` 14% unique, `player_positions` 9%; would take
the store 80 MB → ~30 MB).

### Verification that ran

- Rating engine vs SQL: 36,920 ratings + 3,302 effective ratings, exact match.
- All 6 views + both sheets render under jsdom against the real export, with no
  `undefined`/`NaN`/`[object Object]` in the output.
- All 14 Streamlit pages still pass `AppTest` after the `positions.py` extraction.
- Shortlist round-trip through real R2: an object in the exact shape the Function PUTs was read
  back by `state.py` → `db.shortlist_get()`, id stayed int-coercible, and delete removed it.

---

## Phase 3 — remote-agent SQL access. **OPEN PR, design verified end-to-end, store upload pending**

Full detail: [`agent-context/remote-duckdb-access.md`](agent-context/remote-duckdb-access.md).
Short version: the JSON API only answers fixed shapes; this adds a second path where a remote
agent with no local store can `ATTACH` a scrubbed copy of the DuckDB store and run arbitrary
SQL.

**PR open, unmerged:** https://github.com/ZacHooper/fmm-stats/pull/1 (branch
`claude/duckdb-r2-storage-d1rumw`). This session: got `rclone` installed and real R2 creds
working, **pivoted the design** away from a Worker route (`*.workers.dev` is commonly blocked
in a network-restricted Claude Code sandbox — exactly this feature's target audience) to a
direct DuckDB `ATTACH` over R2's native S3 protocol, then — once the user widened this
sandbox's network policy — **verified the whole path works end to end**: uploaded a probe file
with `rclone`, read it back with a real `duckdb.connect()` / `ATTACH` / `read_text` over
`s3://fmm-stats/...`. Three gotchas found and fixed along the way (full detail in the linked
note):
1. DuckDB's `TYPE r2`/`ACCOUNT_ID` secret shorthand silently mis-routes to public AWS S3 instead
   of R2 in this kind of proxied sandbox — use `TYPE s3` with an explicit `ENDPOINT`,
   `URL_STYLE 'path'`, `REGION 'auto'` instead (confirmed working).
2. `INSTALL httpfs` requests a **plain HTTP** URL by default, which can still 403 even once the
   HTTPS host is allowlisted (host+scheme-specific policies are common) — fetch the `.gz` over
   HTTPS yourself and drop it in `~/.duckdb/extensions/...` instead; `LOAD httpfs` then needs no
   network call at all.
3. `worker/index.js`'s `/api/db` route and `CAREER_RE` constant were removed since nothing
   serves this way anymore; `export_data.py`'s `files.database` key now points at the `s3://`
   key directly.

All docs (`scripts/publish_duckdb.py`'s docstring, `site/AGENTS.md`, `docs/DEPLOY.md`,
`CLAUDE.md`) carry the verified `ATTACH` syntax and both workarounds. A Supabase/Postgres pivot
was considered and rejected: the store is only ~90 MB, so size was never the constraint, and
migrating off DuckDB would mean rewriting the loader + dashboard + `fmq.py` for what was really
just a network-allowlist gap.

**What's NOT done yet:** the real `fm-frem.duckdb` hasn't been re-uploaded and queried with
these fixes applied — the probe-file round trip proves the credential/endpoint path works, but
not yet against the actual store. **Next session should:** run
`uv run python scripts/publish_duckdb.py --career frem --upload`, then run the verified `ATTACH`
snippet against `site-data/fm-frem.duckdb`, confirm `ca`/`pa` come back `NULL` on real rows, and
tick off the PR's test-plan checklist.

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
  Division, £31.7k/yr idle — the standout. (The "4 clubs" in an earlier draft of this file
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
