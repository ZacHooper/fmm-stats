#!/usr/bin/env python3
"""
Where the data lives in the save, and the managed-career config.

Scope: the parser is CAREER-AWARE (see careers.py); the constants here are the
DEFAULT career's, for callers that don't pass one. Two kinds live here:

  * CAREER CONFIG — resolved from careers.py, so it follows whichever career is
    active. Do not read the values below as fixed.

  * REGION WINDOWS — byte ranges where the three big structures sit. These DO
    drift per save AND per career, so they are deliberately generous and every
    record is validated on read (grid phase, value ranges, name shape). If a save
    moves data outside a window, widen it here. Do NOT rely on tests/ to catch
    that: every test skips when its save is absent, which is most of the time.
"""
from .careers import resolve_career

# ---- default managed career ----
# Which club you manage lives in careers.py; pick one per run with
# `extract.py --career <key>` or FM_CAREER. Below is whatever careers.py resolves as the
# default (currently frem) for callers that don't pass one — every hot path threads the
# actual club marker through instead (see player_attributes.py).
_DEFAULT = resolve_career()
MANAGED_CLUB_TID = _DEFAULT.managed_tid       # default career's first team
MANAGED_RESERVE_TID = _DEFAULT.reserve_tid    # its reserve side (AI-run)
LEAGUE_COMP_IDS = _DEFAULT.league_comps
CLUB_MARKER = _DEFAULT.club_marker            # managed club TID (u16 LE) + ff ff

# per-match delimiter cluster (same in every FMM22 save)
DELIM_UNIT = bytes.fromhex("21225515" + "0a000000")

# ---- region windows (generous; validated per-record on read) ----
# global attribute records (keyed by SID, fixed 78-byte grid).
#
# MEASURED 2026-09-20, window vs whole-file, on frem-2021-07-01, frem-2026-06-11 and
# bucaspor-2023-03-25: identical record counts (26,518 / 26,518 / 26,305), so this window
# clips NOTHING on either career. The real extent is 3.977-6.219M, 3.989-6.230M and
# 4.090-6.356M respectively -- about 0.18 MB of margin at the bottom and 0.24 MB at the top,
# which is tighter than it looks. If a future career's table starts below 3.8M the loss would
# be silent, so re-run that comparison rather than trusting this note.
ATTR_LO, ATTR_HI = 3_800_000, 6_600_000
# per-match stat region (home XI then away XI, delimiter-clustered). Still here because
# `matches.match_anchors` takes it as a DEFAULT lo for callers that pass no bounds -- and it
# is 55M, which is INSIDE Frem's own match region (~53.8M), so relying on it drops the start
# of that career. `matches.extract_season` no longer does: it locates, and scans from 0 when
# it cannot. Do not make this a fallback again.
MATCH_LO = 55_000_000
#
# SNAPSHOT_LO/HI and LIGHT_LO/HI USED TO SIT HERE AND ARE DELETED. Both were fallbacks, and
# both had the failure mode this file's own header warns about: they were measured on one
# career, they answer instead of raising, and a blind locator therefore produced a plausible
# short result rather than an error.
#   * SNAPSHOT_LO/HI (62.3-63.2M) was the DEFAULT career's squad snapshot. A career whose
#     snapshot sits elsewhere got an empty answer. `attributes.snapshot_bounds` now raises
#     `SnapshotNotFound`.
#   * LIGHT_LO/HI (47.0-50.5M) was Bucaspor-tuned. Measured across all 34 archived saves in
#     both careers, `lightresults.find_light_regions` returns a region on every one, so the
#     fallback was dead code with a failure mode attached. It now raises `LightRegionError`.
# Do not re-add either. See docs/parser-architecture.md, shapes B and C.
# NOTE: contract-STATUS has no window on purpose. CONTRACT_LO/HI (54M-58M) was exact for
# Bucaspor and 4 MB late for Frem, decoding ZERO of ~25,500 records on two snapshots.
# scrape_contract_status scans the whole file (0.1s) and is safe unwindowed because every hit
# must match tid AND uid from the info spine. Do not re-add a window here.
# player contract DETAIL records — a separate section from the 0x87 status records above.
# Layout: [tid u32][0x01][wage u16 = £/yr÷~520][zeros][expiry day-of-year u16][expiry year u16].
# Wage validated £15.5K–£17.75M (±2%); expiry is a full date (DOB-style day+year). Frem's records
# sit ~29–31M, inside the big 16–38M binary section; the window is generous + validated per-record.
#
# MEASURED 2026-09-20, window vs whole-file: identical on frem-2026-06-11 (26,706) and
# bucaspor-2023-03-25 (26,229). frem-2021-07-01 gains exactly ONE record without the window
# -- and that record is a FALSE POSITIVE, not a loss. tid 263 at 12.646M reads wage_units 0
# and an expiry of 2021-01-01, six months BEFORE that save's own date, and 12.646M sits
# inside the competition table (12.607-12.756M). So this window is doing real work: it is
# excluding a coincidental `[tid][0x01]...[plausible year]` in an unrelated structure.
# Do not widen it to "recover" that record.
CONTRACTREC_LO, CONTRACTREC_HI = 16_000_000, 40_000_000
# £/yr per wage unit (from ground truth: De Bruyne 34000u=£17.75M, Hull/Frem across the range).
WAGE_GBP_PER_UNIT = 520
# club + competition name records. The bound exists because unwindowed, reference.py's
# lookups `mm.find`-scanned the whole ~60 MB per call (a small-int TID packed as 4 mostly-zero
# bytes hits 44k+ false positives in a padded save). No runtime fallback: "windowed, then
# whole file" was measured SLOWER, because most club_record calls in a real extract are MISSES
# and a miss scans to the end of the range either way, so it pays for both scans.
#
# LO=0 is deliberate — setting it from sampled TID hits cut 2.4 MB off the FRONT of the real
# section. Bounds come from the `map_regions.py` "ff-records" section, observed at ~0.57M to
# 16.6-17.5M across 2 careers x 3 years, so HI keeps ~2.5 MB of margin. To widen, prefer
# deriving it from `mapregions.sections()` at runtime over hand-tuning again.
REFDATA_LO, REFDATA_HI = 0, 20_000_000
