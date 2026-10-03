# site — the web app

See also [`AGENTS.md`](AGENTS.md) (query cookbook).

## The web app (one UI for phone and desktop)
`site/` is a static single-page app on Cloudflare Pages — the primary UI, since Streamlit can't be
hosted without a server. Its sections collate the 13 dashboard pages: **Squad** (one configurable
table merging the squad list, Development + projections, Player Stats and Registration — the
A/B lists as a column, the quotas as one hover/tap card, saved windows under the table; see
below), **Builder**, **Recruitment** (search + shortlist + the capital rule), **Matches**,
**History**, **World**. Every owned player's profile sheet ends in a **Loan outlook**
(`site/js/loans.js`, data `api/loans.json`): his Level %ile in each division from ours down to
3. Division, against each club's starter line at his position in its manager's preferred
formation — see `build_loans` in `scripts/_export_db.py`. It ships DATA
and computes on the client, so switching tactic re-rates every player with no rebuild.
**Streamlit stays** for what writes to DuckDB (Tactics, Config) and for Team Builder.
Read [`docs/DEPLOY.md`](docs/DEPLOY.md) before touching it.

### Squad registration is a HOUSE RULE, not something the save models
FMM22 has no A-list, no B-list and no home-grown requirement. The Squad page's registration
columns and card (`site/js/registration.js`) enforce the Danish Herre-DM rules ([`docs/danish-registration-rules.md`](docs/danish-registration-rules.md))
on ourselves: a 25-man A-list needing 8 home grown of whom 4 club-trained (tiers 1–2 only), plus
an unlimited B-list for players under 21 at the last new year. Home-grown status is **derived** —
never report it as a fact the game asserts. The data layer is the registration family in
`fmstats/mart.py` (`mart.squad_registration` for our squad, `mart.player_homegrown` for
everyone, `mart.player_training` for the club-by-club months); the derivation and its two
deliberate departures from a literal reading are in
[`docs/agent-context/homegrown-derivation.md`](docs/agent-context/homegrown-derivation.md) and
[`site/guides/registration.md`](site/guides/registration.md). The A/B plan itself lives in
browser localStorage — it is a plan, not save data, and nothing writes it back. A plan can be
**saved against a transfer window** (`site/js/regwindows.js` → `/api/registrations` →
`state/registrations/<year>-<summer|winter>.json` in R2, same token as the shortlist) as the
history of what was registered and the starting point for the next window.
