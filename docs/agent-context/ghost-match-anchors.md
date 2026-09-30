---
name: ghost-match-anchors
description: "SUPERSEDED 2026-09-30 — matches are read as a count-framed table (tables/matches.py), with no anchors; the anchor scan made phantom 0-0 duplicates and missed each season's first match"
metadata:
  node_type: memory
  type: reference
---

> **SUPERSEDED 2026-09-30.** Matches are no longer found by delimiter anchors: they are a
> count-framed table, one row per match, walked by each row's own length
> (`fmparser/tables/matches.py`). The delimiter cluster was the per-starter tactic items at the
> END of the previous match's row, which is also why the anchor scan never found the season's
> first match. A duplicate cannot arise from a walk that steps row by row. Kept for the lesson
> at the bottom, which still holds for any forward scan.

**Symptom (reported 2026-09).** The site's results list showed Frem playing København and Horsens
one extra time each in 2026 — a second row on the same date against the same opponent, scored 0–0,
with no formation and no stats. The real fixture sat directly above it with the correct score.

**Cause.** `matches.match_anchors` clusters `DELIM_UNIT` hits that are ≤16 bytes apart into one
anchor. A handful of matches carry a *second* delimiter cluster **24 bytes** ahead of the real one
— just far enough to survive as its own anchor. `parse_header` then scans FORWARD from an anchor
for the first plausible `[day][year]`, so the ghost anchor re-reads the very same header and
reports the same date, the same two tids and the same attendance. What it cannot reach is the
football: `extract_match` walks the XI between this anchor and the *next* one, and the next one is
the real anchor 24 bytes later, so the window closes before a single 54-byte stat block. Score 0–0
by summation over an empty XI, formation `None`.

Three of them in `frem-2026-06-29.fms` (2 Frem fixtures, 1 reserve), 2 in the published store —
rare enough to look like a scoreline, common enough to corrupt a season record and every award
built on it.

**Fix** (`matches.extract_season`). The **header offset is the match's identity**: two anchors that
resolve to one `date_off` are one match. Keep the reading with the larger XI rather than trusting
anchor order, so the rule is a statement about content, not about which stray byte landed first.
Verified on `frem-2026-06-29.fms`: 59 headers → 56 matches, zero duplicate `(date, home, away)`
triples, zero of our matches left without an XI.

**Why not widen the clustering gap to 24+.** It would merge the pair, but it would then pick the
GHOST offset as the anchor and hand every downstream reader (`parse_formation`,
`parse_slot_positions`, `find_xis`) a window starting 24 bytes early — trading a visible duplicate
for a silent shift, and touching every match in every save to fix three. Dedupe is narrow and its
failure mode is loud.

**Generalisable lesson.** Anything derived by scanning FORWARD from an anchor (`parse_header` here)
can be reached from more than one anchor, so the anchor is not a key — the thing it resolves to is.
When a parser can emit two records for one object, deduplicate on the resolved offset, and break
the tie on which record has content.
