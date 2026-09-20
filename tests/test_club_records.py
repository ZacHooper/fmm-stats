#!/usr/bin/env python3
"""
Guard the club-records decode against in-game ground truth.

`fmparser/clubrecords.py` reads the region `lightresults.py` has been treating as match
RESULTS since 2026-07. It is the Club History screens instead, and the only thing that
establishes that -- or catches a regression in it -- is a set of values read off the game.

The trap this test exists for is specific and would otherwise pass unnoticed: the club tid
sits at the END of the 21-byte record. A record held in two slots is stored twice in adjacent
rows, so anchoring on the tid and reading the value/cid/day FORWARD is right on the first
copy and silently reads the NEXT record's fields on the second. Half the rows come out
plausible and wrong. Asserting that every copy of a fixture agrees is what catches it.

    uv run python tests/test_club_records.py
"""
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import skip  # noqa: E402

from fmparser import clubrecords as CR      # noqa: E402
from fmparser import staging as S           # noqa: E402
from fmparser.save import Save              # noqa: E402

SAVE = os.path.expanduser("~/fm-saves/frem/frem-2026-06-11.fms")
SOUTHAMPTON = 504

# Southampton's Club History, read off screenshots taken on the 11 Jun 2026 save.
# (opponent_tid, score_for, score_against, day_of_year, value, description)
TEAM_RECORDS = [
    (481, 3, 6, 135, 9.0, "Highest scoring match, 3-6 v Newcastle 16/5/2026 (total goals)"),
    (499, 4, 0, 227, 4.0, "Biggest win 2025/26, 4-0 v Sheff Utd 16/8/2025 (goal difference)"),
    (473, 0, 5, 234, -5.0, "Biggest defeat 2025/26, 0-5 v Man City 23/8/2025 (goal difference)"),
    (473, 0, 5, 280, -5.0, "Biggest defeat overall, 0-5 v Man City 8/10/2022"),
]

# The Team Records - 2025/26 Season screen, slot by slot. The slot index IS the category, so
# this asserts the ORDER as much as the values -- and the order is the only thing that makes
# a row interpretable, since no category id is stored.
TEAM_BLOCK_2025 = [
    ("highest_league_position", 5.0), ("lowest_league_position", 16.0),
    ("highest_scoring_match", 9.0), ("highest_scoring_league_match", 9.0),
    ("biggest_win", 4.0), ("biggest_league_win", 4.0),
    ("biggest_defeat", -5.0), ("biggest_league_defeat", -5.0),
    ("most_consecutive_wins", 2.0), ("most_games_without_defeat", 4.0),
    ("most_games_without_win", 5.0), ("most_consecutive_defeats", 3.0),
]

# Player Records - Overall, slot by slot, with the player the game names.
PLAYER_BLOCK = [
    ("most_goals_in_a_season", 17.0, "Lino"),
    ("most_league_goals_in_a_season", 16.0, "Lino"),
    ("most_assists_in_a_season", 12.0, "Aribo"),
    ("highest_average_rating_in_a_season", 7.37, "Sterling"),
    ("most_player_of_match_in_a_season", 7.0, "Woodman"),
    ("most_bookings_in_a_season", 16.0, "Ward-Prowse"),
    ("most_red_cards_in_a_season", 1.0, "Broja"),
    ("most_appearances_in_a_season", 44.0, "Bednarek"),
    ("youngest_player", 6182.0, "Woodman"),
    ("oldest_player", 13212.0, "Forster"),
    ("highest_transfer_fee_paid", 31156734.0, "Nygren"),
    ("highest_transfer_fee_received", 44958444.0, "Livramento"),
]

# Player Records - Overall. The last two are ages expressed in DAYS: 16y338d and 36y63d come
# out as years*365.25 + days, exactly, which is what identified the table in the first place.
PLAYER_VALUES = [
    (12.0, "Most assists in a season - J. Aribo 12 (2025/26)"),
    (7.37, "Highest av. rating - D. Sterling 7.37 (2024/25)"),
    (44.0, "Most appearances - J. Bednarek 44 (2022/23)"),
    (6182.0, "Youngest player - T. Woodman 16 yrs 338 days"),
    (13212.0, "Oldest player - F. Forster 36 yrs 63 days"),
    (31156734.0, "Highest fee paid - B. Nygren (shown as GBP 31M)"),
    (44958444.0, "Highest fee received - T. Livramento (shown as GBP 45M)"),
]


def main():
    if not os.path.exists(SAVE):
        return skip(f"{os.path.basename(SAVE)} not found (fetch with rclone or rebuild.py)")
    mm = Save(SAVE).mm
    info = S.scrape_players(mm)
    valid = {v["club_tid"] for v in info.values()
             if v.get("club_tid") and v["club_tid"] != S.NO_CLUB}
    built = CR.build(mm, valid)
    team = [r for r in built["team_records"] if r["club_tid"] == SOUTHAMPTON]
    player = [r for r in built["player_records"] if r["club_tid"] == SOUTHAMPTON]
    ok = True

    print(f"Southampton: {len(team)} team-record rows, {len(player)} player-record rows\n")

    print("TEAM RECORDS vs the game:")
    for opp, sf, sa, day, value, label in TEAM_RECORDS:
        hits = [r for r in team if r["opponent_tid"] == opp and r["score_for"] == sf
                and r["score_against"] == sa and r["day"] == day]
        good = hits and all(abs(r["value"] - value) < 1e-6 for r in hits)
        ok &= bool(good)
        got = sorted({round(r["value"], 2) for r in hits}) or "none"
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good:
            print(f"        expected value {value}, got {got} across {len(hits)} row(s)")

    print("\nCOLUMN-OFFSET GUARD: every copy of a MATCH record must agree on its value")
    # Restricted to rows that are demonstrably match records -- ones whose value equals the
    # scoreline's total goals or goal difference. STREAK rows ("most games without a win")
    # carry a streak length with leftover opponent/score bytes, so requiring them to agree
    # would assert something untrue: Southampton's Leicester 4-2 rows hold 5.0 and 3.0, which
    # are its real 2025/26 streaks, not anything to do with that scoreline.
    by_fixture = defaultdict(set)
    for r in team:
        if r["kind"] != "match" or r["score_for"] is None:
            continue          # table/streak rows have no fixture; the parser nulls them out
        total = r["score_for"] + r["score_against"]
        gd = r["score_for"] - r["score_against"]
        if abs(r["value"] - total) < 1e-6 or abs(r["value"] - gd) < 1e-6:
            by_fixture[(r["opponent_tid"], r["score_for"], r["score_against"],
                        r["day"])].add(round(r["value"], 4))
    disagree = {k: v for k, v in by_fixture.items() if len(v) > 1}
    ok &= not disagree
    print(f"  {'ok  ' if not disagree else 'FAIL'} {len(by_fixture)} match record(s) checked, "
          f"{len(disagree)} disagree across copies")
    for k, v in list(disagree.items())[:3]:
        print(f"        opp={k[0]} {k[1]}-{k[2]} day={k[3]} -> values {sorted(v)}")

    print("\nCATEGORY ORDER — Team Records, 2025/26 block (slot index == category):")
    blocks = defaultdict(list)
    for r in team:
        blocks[r["offset"] - r["slot"] * 21].append(r)
    target = None
    for base, rows in blocks.items():
        bw = [x for x in rows if x["category"] == "biggest_win"]
        if bw and bw[0]["day"] == 227:
            target = sorted(rows, key=lambda r: r["slot"])
            break
    if target is None:
        ok = False
        print("  FAIL could not find the 2025/26 block (biggest_win on day 227)")
    else:
        for (cat, val), row in zip(TEAM_BLOCK_2025, target):
            good = row["category"] == cat and abs(row["value"] - val) < 1e-6
            ok &= good
            print(f"  {'ok  ' if good else 'FAIL'} slot {row['slot']+1:>2} {cat:<30} "
                  f"{row['value']:>7.2f} (expected {val})")

    print("\nPLAYER RECORDS — Overall block, slot / value / player:")
    from fmparser import reference as R
    pblocks = defaultdict(list)
    for r in player:
        pblocks[r["offset"] - r["slot"] * 22].append(r)
    pt = None
    for base, rows in pblocks.items():
        if any(abs(x["value"] - 44958444.0) < 1 for x in rows) and \
           any(x["season"] == 2025 for x in rows):
            pt = sorted(rows, key=lambda r: r["slot"])
            break
    if pt is None:
        ok = False
        print("  FAIL could not find the Overall player block")
    else:
        R.build_name_resolver(mm)
        for (cat, val, who), row in zip(PLAYER_BLOCK, pt):
            p = info.get(row["player_tid"])
            nm = R.resolve_name(mm, p["first_name_id"], p["last_name_id"]) if p else ""
            good = (row["category"] == cat
                    and abs(row["value"] - val) < max(0.005, abs(val) * 1e-6)
                    and who.lower() in str(nm).lower())
            ok &= good
            print(f"  {'ok  ' if good else 'FAIL'} slot {row['slot']+1:>2} {cat:<34} "
                  f"{row['value']:>14,.2f}  {nm} (expected {who})")

    print("\nPLAYER RECORDS vs the game:")
    have = [r["value"] for r in player]
    for value, label in PLAYER_VALUES:
        hit = any(abs(v - value) < max(0.005, abs(value) * 1e-6) for v in have)
        ok &= hit
        print(f"  {'ok  ' if hit else 'FAIL'} {label}")

    print("\n" + ("PASS: club records match the game" if ok else "FAIL: see above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
