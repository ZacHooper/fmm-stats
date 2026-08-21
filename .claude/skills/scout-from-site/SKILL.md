---
name: scout-from-site
description: Scout an upcoming opponent using the DEPLOYED site's JSON API instead of the local DuckDB store — works from a phone, or from any machine, with no save file, no store and no Streamlit. Use when the user asks to scout a team and the store isn't available or isn't current, when they're away from the machine that holds it, or when they explicitly say "from the site" / "over the API". For a full-depth report on a machine that HAS the store, prefer scout-opponent.
---

# Scout an opponent from the deployed site

Same job as [`scout-opponent`](../scout-opponent/SKILL.md), different data source: the static JSON
published by `scripts/export_data.py` rather than the local DuckDB store. Use this when the store
isn't to hand — the point of the site is that a scouting report doesn't need a laptop awake.

## What you lose, and should say so

The site is **one snapshot** (whichever `export_data.py` last published), and it carries less than
the store does:

- No match-by-match `light_results` beyond what `matches.json` holds.
- Ability *ranks* only for our own squad (`positions.json`); for an opponent you get ability
  *percentiles* per player-position, not their rank inside another division.
- No injury or loan-spell history, no awards tables, no per-competition league detail.

If the answer needs any of those, say the store would answer better and offer to run
`scout-opponent` instead. Don't quietly deliver a thinner report as if it were the full one.

## The source of truth is on the site, not in this file

**Fetch these two and follow them.** They are versioned with the data, so they can't drift out of
step with the schema the way a copy in this repo would:

1. `<SITE>/AGENTS.md` — the columnar format, the rating formula you must compute yourself, the
   immersion rule, and the caveats.
2. `<SITE>/guides/scout.md` — the scouting procedure and output shape.

`<SITE>` is the Cloudflare Pages URL. Resolve it in this order: the `FM_SITE` environment
variable, then the `site.url` line in `docs/DEPLOY.md` if present, then ask the user. Don't guess a
project name — the URL is deliberately unguessable.

For a local check with no deployment, `uv run python -m http.server -d site 8000` serves the same
files at `http://localhost:8000` (both Functions are absent, so `/api/all` falls back to
`site/api/all.json` on disk).

## The two things that trip agents up

- **Ratings are not in the data.** `rating = SUM(attribute × weight)` from
  `core.tactics[method][role]`, where an attribute the role doesn't list weighs **1**, and the keys
  there are **lowercase**. Then `effective = rating × famMult(fam)`. `AGENTS.md` carries a worked
  example with a known answer — check your arithmetic against it before you report anything.
- **Rows are positional arrays**, with a sibling `*_fields` array naming the slots. Zip them.

## Non-negotiables

- **Ask for the in-game scout's formation and style.** Opponent shape is not in the save and cannot
  be derived. Do the squad-profile half while you wait if you like, but label it provisional.
- **Never surface a raw ability number**, and never reconstruct one. Percentiles, ranks, attributes
  and match stats only. The export omits it deliberately.
- **Opponent attributes are model estimates (±1)** outside pace and physicals — don't hang an
  argument on one point.
- **Say what's stale.** Report the snapshot date from `index.json` in the briefing; if it's from
  before the current transfer window, the squad you're describing may not be the squad they field.
