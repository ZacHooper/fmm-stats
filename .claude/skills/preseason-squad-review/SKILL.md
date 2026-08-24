---
name: preseason-squad-review
description: Data-driven pre-season squad review for the active FM career — best XI + bench for the current formation, loan candidates, fast-growing youth, and validation that the rating weighting matches actual match output. Use each pre-season (after importing the new season-start save) or when the user asks to analyse the team / pick a starting XI / decide loans.
---

# Pre-season squad review

Reads the active career's store, `fm-<key>.duckdb` (build/refresh via the `import-fm-saves` skill
first). Combine **attribute-weighted ratings** (talent/profile) with **actual match output**
(performance) — neither alone is enough. Immersion rule: reason with ratings + match stats,
**never surface CA/PA**.

## Inputs to establish first
- **Formation & roles** — ask the user. Map their roles → rating roles (WB→LB/RB, CD→CB, RP→DM,
  B2B→CM, IF→AML/AMR, AF→ST).
- **Which tactic (method)** — read it, don't assume: `db.config().get("default_method")`
  (Frem → `frem_attacking_ss`; `buca_433` belongs to the archived Turkish career).
- **Snapshot** — the latest one: `db.latest_snapshot()`, or
  `SELECT season, phase FROM mart.snapshots ORDER BY season DESC, phase_ord DESC LIMIT 1`.
  **Phases are in-game DATES (`YYYY-MM-DD`), not the words `start`/`mid`/`end`** — a query
  hardcoding `phase='start'` returns zero rows on any current store.
- **Squad** — `mart.squad_on(<date>)`, which resolves membership from spells. Do **not** filter on
  `staging.players.loaned_in`: that flag is set-only and never cleared, so it accumulates expired
  loans (9 flagged at Frem's latest snapshot, 6 of them gone for a year or more).
- **First team vs reserves** — `mart.managed_club` and `mart.reserve_clubs`. Use `managed_club`
  for match stats; `mart.our_clubs` (both) for squad membership.

## Core query patterns (open read-only; a running Streamlit holds the write lock)

**Effective rating per player×position** (familiarity-adjusted). Prefer the shared helper —
`db.effective_table(season, phase, method)` — so the app and this review can't diverge. Raw SQL
equivalent, if you need it:
```sql
select pp.tid, prm.role, pp.familiarity, r.rating base,
       r.rating*(0.5+0.5*pp.familiarity/20.0) eff, p.name, p.dob, p.club_tid
from staging.player_positions pp
join staging.position_role_map prm on prm.position=pp.position
join v_player_ratings r on (r.season,r.phase,r.tid)=(pp.season,pp.phase,pp.tid)
     and r.method=<method> and r.role=prm.role
join staging.players p on (p.season,p.phase,p.tid)=(pp.season,pp.phase,pp.tid)
where (pp.season,pp.phase)=(<S>,<P>)
  and p.club_tid in (select club_tid from mart.our_clubs) and not p.is_staff
```
Dedupe to best eff per (tid, role) — a player can have two position codes mapping to one role.

**Match stats — from `mart`, split first-team vs reserve by `team_tid`.** `mart.player_seasons`
has apps/starts/minutes/rating already computed, appearance-filtered and deduped to one phase per
season:
```sql
select person_id, sum(apps) apps, sum(starts) starts, sum(minutes) mins,
       round(sum(avg_rating*apps)/nullif(sum(apps),0),2) mr,
       sum(goals) g, sum(assists) a, sum(key_passes) kp
from mart.player_seasons
where season=<Y> and team_tid in (select club_tid from mart.managed_club)
group by person_id
```
> Never aggregate `staging.match_player_stats` directly: it is a ring buffer re-scraped every
> import, so summing without a phase filter multiplies every total by the number of snapshots in
> that season. And an unused sub still gets a row carrying a flat **6.00** rating — average it in
> and every figure sags toward 6.

**Development** — `mart.player_growth_season` (this season) and `mart.player_growth_tenure`
(since he signed; a season alone badly understates a long server). Filter `growth_comparable` to
drop the estimate→exact artifact a new signing produces. `age` comes from these views.

**Growth** — best attribute-weighted `base` rating per (tid,label) across all labels; delta
latest − earliest. Focus U24.

## Deliverables (the review)

1. **Best XI** for the formation: per role, rank squad by effective rating, then **cross-check
   with match output** (minutes, goals, avg match rating). Pick the top per slot, no duplicates.
   Where rating and output disagree, **trust output** — especially at **ST** (see gotcha).
2. **Bench of 7** covering GK / DEF / MID / ATT; prize versatile utility players.
3. **Loan candidates**: U24, low **first-team** minutes, blocked behind better players at a
   stacked position. Distinguish reserve minutes (a reserve regular ≠ first-team ready). Flag the
   truly starved (≈0 minutes anywhere) as top priority.
4. **Reserve standouts**: high reserve output (goals/assists, avg rating) = promotion or
   start-somewhere-senior loan candidates (e.g. a reserve top scorer with no first-team minutes).
5. **Fast growers**: biggest rating deltas, especially U24 — the trajectory players to protect.
6. **Weighting validation**: does rating rank track match output? Confirm the agreements; flag
   the outliers. Propose weighting tweaks (clone a tactic on the Tactics page) where a role's
   weighting is clearly off for this league/match-engine.
7. **Succession / youth-save note**: this is a **youth-only save (no transfers)** — call out
   aging positions with no young cover (currently CB: only 17yo Binici; DM: none) and suggest
   retraining or tactical adaptation, not signings.

## Gotchas (learned the hard way)
- **Reserve vs first-team split is essential** — always split by team_tid; combining them
  overstates fringe players' first-team roles.
- **Striker rating is the least reliable** — attribute weighting predicts ST goals poorly here
  (a poacher can overperform a "better" profile; a great-profile winger can under-return). For
  strikers, **select on goals/90**; use rating only to scout. Restrict a role's comparison to
  players who actually play it (don't rank a winger as an ST).
- **Familiarity matters**: use effective rating (× familiarity), not base, for selection.
- **No per-90 without the minutes decode** above; matches assume 90' (ET undercounted).
- Kill any running Streamlit before opening the DB read-write; read_only for pure analysis.
