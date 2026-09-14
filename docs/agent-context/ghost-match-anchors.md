---
name: ghost-match-anchors
description: "FIXED — a second delimiter cluster 24 bytes ahead of a real match made phantom 0-0 duplicate fixtures; dedupe on the header offset, which is the match's identity"
metadata:
  node_type: memory
  type: reference
---

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
