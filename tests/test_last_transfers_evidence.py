#!/usr/bin/env python3
"""
Evidence for `last_transfers` (`fmparser/tables/last_transfers.py`, docs/parser/last_transfers.md).

On every save found among the eight below: one row per player attribute record, every row
dated the save's own header date, and no filled row on a career's first days. On the saves
measured, a filled row's tid is the person whose attribute record the row is (all on Truro,
98% on Frem, where retired players' slots are reused). On truro-2026-08-08, checked
against the transfer band (read inline here; it has no parser table): every filled row is a
player with an accepted bid, the buying club and fee those of the bid on nearly every row,
and Amir Rrahmani's row is the 8,846,250 move from Parthenope to Ipswich Town.

    uv run python tests/test_last_transfers_evidence.py
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import last_transfers, loans_table_spans, tables_for  # noqa: E402
from fmparser.tables.person_info import scrape_person_info  # noqa: E402
from fmparser.tables.save_header import read_save_header  # noqa: E402

SAVES = ["frem-2021-06-27.fms", "frem-2023-07-02.fms", "frem-2026-06-11.fms",
         "frem-2030-06-22.fms", "bucaspor-2023-04-01.fms", "truro-2026-07-22.fms",
         "truro-2026-07-25.fms", "truro-2026-08-08.fms"]
FILLED = {"frem-2021-06-27.fms": 0, "frem-2026-06-11.fms": 10323, "truro-2026-07-22.fms": 0,
          "truro-2026-08-08.fms": 428}
RRAHMANI = {"tid": 3915, "fee": 8846250, "club": "Ipswich Town"}

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def accepted_bids(mm):
    """{player tid: [(buying club, fee)]} from the transfer band's `0d` rows."""
    lo = loans_table_spans(mm)[0][1]
    sig, at = struct.pack("<I", 65000), mm.find(struct.pack("<I", 65000), lo)
    while at != -1:
        n = struct.unpack_from("<I", mm, at + 4)[0]
        if 0 < n < 65000 and struct.unpack_from("<I", mm, at + 10 + 109)[0] == 0:
            break
        at = mm.find(sig, at + 1)
    out = {}
    for k in range(n):
        o = at + 10 + 143 * k
        if mm[o] == 0x0D:
            out.setdefault(struct.unpack_from("<I", mm, o + 6)[0], []).append(
                (struct.unpack_from("<H", mm, o + 103)[0], struct.unpack_from("<I", mm, o + 87)[0]))
    return out


def check_save(name):
    path = find_save(name)
    if not path:
        return False
    mm = Save(path).mm
    print(f"\n{name}")
    loc = last_transfers.locate_last_transfers(mm)
    check(loc is not None, "the table is found")
    if loc is None:
        return True
    attrs = tables_for(mm)["player_attributes"].scrape(mm)
    check(loc[1] == len(attrs), f"one row per player attribute record ({loc[1]:,})")
    rows = last_transfers.scrape_last_transfers(mm)
    day = read_save_header(mm)["date"]
    base = loc[0]
    stamps = {bytes(mm[base + k * 30 + 26:base + k * 30 + 30]) for k in range(loc[1])}
    check(len(stamps) == 1 and all(r["as_of"] == day for r in rows),
          f"every row is dated the save's day, {day}")
    if name in FILLED:
        check(len(rows) == FILLED[name], f"{FILLED[name]:,} filled rows")
    persons = scrape_person_info(mm)
    tid_by_sid = {p["sid"]: t for t, p in persons.items() if p["sid"] != "ffffffff"}
    own = sum(tid_by_sid.get(attrs[r["row"]]["sid"]) == r["tid"] for r in rows)
    check(not rows or own / len(rows) > 0.98,
          f"a row's player is its attribute record's person ({own:,}/{len(rows):,})")
    if name == "truro-2026-08-08.fms":
        bids = accepted_bids(mm)
        check(all(r["tid"] in bids for r in rows), "every filled row has an accepted bid in the band")
        buyer = sum(any(b == r["club_tid"] for b, _ in bids[r["tid"]]) for r in rows)
        fee = sum(any(f == r["fee"] for _, f in bids[r["tid"]]) for r in rows)
        check(buyer >= 420 and fee >= 410, f"buying club {buyer}/428 and fee {fee}/428 as the bid's")
        clubs = {c["tid"]: c["name"] for c in tables_for(mm)["clubs"].scrape(mm)}
        rr = [r for r in rows if r["tid"] == RRAHMANI["tid"]]
        check(len(rr) == 1 and rr[0]["fee"] == RRAHMANI["fee"] and clubs[rr[0]["club_tid"]] == RRAHMANI["club"],
              "Rrahmani: 8,846,250 to Ipswich Town")
    return True


def main():
    ran = [check_save(n) for n in SAVES]
    if not any(ran):
        return skip("none of the last_transfers evidence saves found")
    print(f"\n{'FAIL' if failures else 'PASS'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
