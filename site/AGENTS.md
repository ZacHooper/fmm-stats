# site — the web app (guide for agents working ON it)

[`API.md`](API.md) is the other guide: for agents READING the deployed site's data. It is
published with the app; this file is not (`.assetsignore`).

## The web app (one UI for phone and desktop)
`site/` is a static single-page app served by a Cloudflare Worker with static assets. No build
step: plain ES modules. Its data is not in git: `scripts/export_data.py` writes
`site/api/<career>/*.json` locally (what `python -m http.server -d site` previews) and `--upload`
puts it in R2, where `site-worker/index.js` serves it. **One site, several careers**:
`api/careers.json` (`[site] careers` in fmm.toml) lists them, the header's switcher picks one
(`?career=` in the URL, else the last opened, else the default) and reloads onto it; an archived
career (`active = false`) is shown as last exported. `data.js` reads every file through `api()`,
a Worker state call through `stateUrl()` (shortlist and registration windows are per career),
and a browser-stored plan or pick that names players by tid through `lsCareerGet`/`lsCareerSet`,
because a tid means a different player in another save. Its sections: **Squad** (one configurable
table merging the squad list, Development + projections, Player Stats and Registration — the
A/B lists as a column, the quotas as one hover/tap card, saved windows under the table; see
below), **Builder**, **Recruitment** (search + shortlist + the capital rule), **Matches**,
**History**, **World**. Every owned player's profile sheet ends in a **Loan outlook**
(`site/js/loans.js`, data `api/loans.json`): his Level %ile in each division from ours down to
3. Division, against each club's starter line at his position in its manager's preferred
formation — see `build_loans` in `scripts/_export_db.py`. It ships DATA
and computes on the client, so switching tactic re-rates every player with no rebuild. **Transfers** (`site/js/transfers.js`, data `api/transfers.json` from `site.transfers`)
show on History (the Signings and Sales boards, a Transfers tab, spent / received / net on
each season) and as World's Transfers tab (the market season by season and the world record).
The file ships our own moves whole and the world market summarised per season in SQL — the
career holds ~4,500 moves a season, which no page lists. An opponent's name on **Matches** opens its **club sheet**
(`site/js/club.js`, data in `api/matches.json`): manager, shapes and our record as tiles, then
tabs for the expected XI (in the shape it last played us, or its manager's), the squad, and every
meeting with its line-up and who hurt us at both ends.
**Club colours** are each club's home shirt (`core.json` clubs: `shirt`, from
`dim_club.shirt_colours`), drawn by `ui.js` as a split dot beside a club's name (`clubDot`,
`clubName`) and a band across the club sheet and a player's sheet, in his club's (`shirtStyle`).
They mark identity only: never colour a number, a bar or a row with them, because a club in
red or green would read as the site's bad or good.
**FMM27-only match data** (xG, clear-cut chances, goals conceded, fouls, who assisted whom) is
null on an FMM22 match: `D.statOffered` hides those stats for a career with none, the Matches
page's Partnerships tab shows only when a goal has an assister, and Team stats drops a row no
match records. **Offline**: `sw.js` caches every file here plus the open career's data files and
`/api/<career>/all`, network first — a new file under `site/` must be added to its `SHELL` list,
a new export file to its `DATA` list (`tests/test_site_offline.py` checks). See [`docs/DEPLOY.md`](../docs/DEPLOY.md#offline).
Read [`docs/DEPLOY.md`](../docs/DEPLOY.md) before touching the deploy.

### Squad registration is a HOUSE RULE, not something the save models
A self-imposed constraint the game has no notion of: no squad list, no B-list, no home-grown
requirement. Each career names a **rule set** (`registration` in `fmm.toml`: `denmark`, the
default, `england`, or `none`); the sets are rows of `seeds/registration_rules.csv`, one per
range of league tiers, and the managed league's tier picks the row
(`site.registration_rules`), so a promotion switches the rules. `denmark` is the Herre-DM rules
([`docs/danish-registration-rules.md`](../docs/danish-registration-rules.md)): a 25-man A-list
needing 8 home grown of whom 4 club-trained (tiers 1–2 only), plus an unlimited B-list for players
under 21 at the last new year. `england` is the EFL and National League rules
([`docs/english-registration-rules.md`](../docs/english-registration-rules.md)): a 22-man squad
list with 8 home grown (FA or FAW clubs) in Leagues One and Two, under-21s and goalkeepers exempt,
no cap below. The Squad page's registration columns and card (`site/js/registration.js`) take
their labels and quotas from the rules; in the code A is the capped list and B the free one.
The card's **Count as** picker recounts the plan against another tier of the same rule set
(`site.registration_rule_set`, `ruleSet` in `registration.json`). Home-grown status is **derived** —
never report it as a fact the game asserts. The data layer is `site.registration` and
`site.registration_rules` (`fmstats/models/site/`); the derivation and its two
deliberate departures from a literal reading are in
[`docs/agent-context/homegrown-derivation.md`](../docs/agent-context/homegrown-derivation.md) and
[`guides/registration.md`](guides/registration.md). The A/B plan itself lives in
browser localStorage — it is a plan, not save data, and nothing writes it back. A plan can be
**saved against a transfer window** (`site/js/regwindows.js` → `/api/registrations` →
`state/registrations/<year>-<summer|winter>.json` in R2, same token as the shortlist) as the
history of what was registered and the starting point for the next window.
