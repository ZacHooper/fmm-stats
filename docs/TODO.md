# TODO — the single register of outstanding work

**Everything not-yet-done lives here.** Handoff docs describe work that is *finished* or a
*method* worth keeping; this file is the list of what is still open. If you finish something,
delete its entry — do not mark it done, or this becomes another changelog.

Last reviewed **2026-09-17**, after PR #51 (record expansion + attribute decoder rebuild).

---

## Blocked / needs a decision from Zac

### 1. The R2 API token has never been rolled
Its access key and secret were pasted into a chat transcript. Cloudflare → R2 → Manage API
Tokens, then `rclone config update r2 access_key_id <NEW> secret_access_key <NEW>`. **This is
the only security item in this file.**

---

## Parser / decode

### 2. The league standings record is decoded but not implemented
`staging.standings` still reads `source = 'lightresults_computed'` — the *approximate* table
inferred from partial fixture coverage. A **14-byte fixed record holding the exact final
position of every club in every loaded competition** was decoded on 2026-07-20 and never
wired up. Layout and plan: [`STANDINGS_HANDOFF.md`](STANDINGS_HANDOFF.md). Strict upgrade over
what ships today.

### 3. Complete results/fixtures via a date search
[`DATE_SEARCH_HANDOFF.md`](DATE_SEARCH_HANDOFF.md) — the known results region is a partial feed
(91 of 306 fixtures), and two zones that light up on a date search (~36–38 MB, ~63–64 MB) have
never been examined. **Possibly superseded by #3**: if the standings record gives exact final
tables, complete fixtures may no longer be needed. Decide that before spending time here.

### 4. Staff record bytes `+34..+38` are undecoded
Five catalog indices, declared `UNKNOWN` in `scripts/audit_records.py`'s `LAYOUTS` so the audit
passes honestly. The record's stride and coverage are proven; only these five are unnamed.

### 5. 17% of origin clubs do not resolve, and the capital rule silently under-reports
**3,936 of 22,624** origin clubs come back as `#<tid>` in `mart.player_origin.origin_club`, so
the capital-province rule **cannot be evaluated** for that share of the pool — and
`eligible=False` is currently indistinguishable from *unknown*. Confirmed live: Samuel
Clemmensen (tid 8834) read `#65192`; Zac identified it in-game as FC Fredericia (genuinely
ineligible), but the data could not say so. These ids are **not** in `staging.clubs`, so they
are probably youth/academy or defunct-club records in another structure.

Two things to do: find where they resolve, and until then make `player_origin` distinguish
*ineligible* from *unknown*. **Treat `eligible=False` on a `#<tid>` origin as "ask Zac", not
"no".**

---

## Models

### 6. Refit the transfer-value model with the new reputation fields
`current_reputation` and `world_reputation` are parsed (PR #51) and currently unused.
`fmparser/value_model.py`. This was the one workstream from the parser expansion that never
got done, and reputation is exactly what a value model wants.

### 7. Attribute decoder — two measured leads
Both from [`ATTRIBUTE_MODEL_HANDOFF.md`](ATTRIBUTE_MODEL_HANDOFF.md); neither is speculative.

- **Bias is almost the whole story.** `|mean signed error|` correlates **−0.91** with the
  exact-match rate across the 14. The misses are systematic, not noisy — an intercept problem,
  which is the most fixable kind.
- **We under-predict good players.** Exact falls 83.6% (true 4–6) → 22.4% (true 16–20) with the
  bias going +0.10 → −1.01. Worst precisely where scouting cares most.

Current state is 59.4% exact on Frem / 59.5% on Bucaspor for the nine outfield attributes,
against a **94.8% ceiling**. Read the handoff's "already ruled out" section first — height,
the CA constraint, the CA surprise, a non-linear link and `blend_w` are all tested and dead.

### 8. Goalkeeper attributes cannot be modelled at this sample size
Frem has **7 goalkeepers**. The five keeper attributes are deliberately **not refitted**
(`--min-players`, default 20) and keep the frozen coefficients, because refitting made the
Bucaspor hold-out worse. Needs more GK ground truth before it can move — which realistically
means more careers, not more snapshots (the learning curve is flat in rows and only bends in
players).

---

## Football (the actual career)

### 9. Position write-ups still owed
Zac asked for the position-by-position read for **DM, CM, AML, AMC, AMR and ST**, plus a verdict
on the **4-1-2-2-1** question. GK/LB/RB/CB were delivered. **Note the earlier analysis is now
several seasons stale** — it was written when Frem were in NordicBet Liga; they have been in the
**3F Superliga (tier 1, cid 2) since 2025** and the store now runs to **2027 / 2026-07-02**.
Redo the read against the current squad rather than resuming the old one.

---

## Housekeeping (safe to do any time)

- **~308 MB of stale `output/` dirs** from old experiments (`frem-patched-test`,
  `multi-region-test`, `frem-22-start`, pre-rename leftovers). All regenerable.
  Careful: `rebuild.py --skip-existing` reuses these, and a stale-FORMAT extract used to load
  silently — now guarded by `_extract_is_current`, but deleting them is still tidier.
- **`~/fm-parser-git-backup-20260820.tar`** (302 MB) and `/tmp/oldgit` — the pre-history-rewrite
  backup, safe to delete now the rebuild is verified.
- **4 saves in `unfiled/`** with no in-game date, so no canonical name:
  `frem/unfiled/denmark-mid-22.fms`, `bucaspor/unfiled/{22-23-start, fm_save1-24-mid,
  fm_save3}.fms`. Needs Zac's in-game dates to file them.
- **Stale commit SHAs** cited in `agent-context/fm-parser-project.md` and
  `day1-league-membership.md` (`aac6cbe`, `0b9a679`, `9c89633`, `d0f60af`) — invalidated by the
  history rewrite. Cosmetic.
- **The Cloudflare Pages project does not exist** — the site is deployed as a Worker instead
  (see `DEPLOY.md`). Preview locally with `uv run python -m http.server -d site 8000`.
