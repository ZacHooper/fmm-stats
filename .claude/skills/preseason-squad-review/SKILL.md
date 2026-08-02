---
name: preseason-squad-review
description: Data-driven pre-season squad review for the FM Bucaspor save — best XI + bench for the current formation, loan candidates, fast-growing youth, and validation that the rating weighting matches actual match output. Use each pre-season (after importing the new season-start save) or when the user asks to analyse the team / pick a starting XI / decide loans.
---

# Pre-season squad review

Reads `fm.duckdb` (build/refresh via the `import-fm-saves` skill first). Combine **attribute-
weighted ratings** (talent/profile) with **actual match output** (performance) — neither alone is
enough. Immersion rule: reason with ratings + match stats, **never surface CA/PA**.

## Inputs to establish first
- **Formation & roles** — ask the user (current default: 4-3-3 with a DM: GK / WB WB / CD CD /
  RP(DM) / B2B B2B / IF AF IF). Map roles → rating roles: WB→LB/RB, CD→CB, RP→DM, B2B→CM,
  IF→AML/AMR, AF→ST.
- **Which tactic (method)** — the user's is `buca_433` (default). Use it.
- **Snapshots**: current squad = latest `(season,'start')` label (attributes/ratings + youth
  intake). Match performance = the **latest completed season** (`end` phase, most matches).
- **Squad = OUR_CLUBS (6567 first team + 11320 reserves).** Loaned-out players sit in reserves
  (club_tid 11320, loaned_out=true) so they're included.

## Core query patterns (duckdb, read_only; kill Streamlit first to release the lock)

**Effective rating per player×position** (familiarity-adjusted; floor-0.5 linear multiplier):
```sql
select pp.tid, prm.role, pp.familiarity, r.rating base,
       r.rating*(0.5+0.5*pp.familiarity/20.0) eff, p.name, p.dob, p.club_tid, p.loaned_out
from staging.player_positions pp
join staging.position_role_map prm on prm.position=pp.position
join v_player_ratings r on (r.season,r.phase,r.tid)=(pp.season,pp.phase,pp.tid)
     and r.method='buca_433' and r.role=prm.role
join staging.players p on (p.season,p.phase,p.tid)=(pp.season,pp.phase,pp.tid)
where pp.season=<Y> and pp.phase='start' and p.club_tid in (6567,11320) and not p.is_staff
```
Dedupe to best eff per (tid, role) — a player can have two position codes mapping to one role.

**Match stats — SPLIT first-team vs reserve by team_tid** (6567 vs 11320), appeared-only,
with starts & minutes (see the appearance-decode: pos_order≤11=start; appeared = start OR
subOn<>255; minutes = (subOff or 90) − (subOn or 0)):
```sql
select tid, count(*) apps, sum(case when pos_order<=11 then 1 else 0 end) starts,
  sum(case when subOff=255 then 90 else subOff end - case when subOn=255 then 0 else subOn end) mins,
  round(avg(rating),2) mr, sum(goals) g, sum(assists) a, sum(keyPass) kp
from staging.match_player_stats
where season=<Y> and phase='end' and team_tid=<6567 or 11320> and (pos_order<=11 or subOn<>255)
group by tid
```

**Age** ≈ `<season_end_year> - year(dob)` (approximate).

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
