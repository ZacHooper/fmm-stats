#!/usr/bin/env python3
"""
Ground-truth guard for the club reference index's uid gate.

For its whole life the club scan accepted only `1 <= uid <= 400_000_000`, which silently
dropped every club whose uid sits in the ~2-billion band -- 327 clubs in a 2026 Frem save,
363 in a 2022 Bucaspor save. Players were assigned to them, so they surfaced as `#6863`
where a club name belonged.

The two names below are read off IN-GAME PLAYER PROFILES (25 Apr 2026), which is what makes
this ground truth rather than a restatement of what the parser already does:

  * Shawn Beeckaert  plays for tid 6863, shown as "EM United"   -> Erpe-Mere United
  * Jesús Bernal     plays for tid 7153, shown as "Paracuellos" -> C.D. Paracuellos Antamira

Requires a 2026 Frem save (gitignored). Pass one, else the canonical name is looked for in
$FM_SAVES_DIR. Skips cleanly if none is found.

    uv run python tests/test_club_uid_gate.py [path/to/frem-2026-03-22.fms]
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.save import Save                        # noqa: E402
from fmparser import reference as R                   # noqa: E402

# tid -> (long name, short name as the game displays it). The first two are the screenshot
# ground truth; the other three came out of the same band and are held so a future gate
# change that drops them fails here.
EXPECTED = {
    6863: ("Erpe-Mere United", "EM United"),
    7153: ("C.D. Paracuellos Antamira", "Paracuellos"),
    6879: ("Fuenlabrada B", "Fuenlabrada B"),
    7113: ("Brøndby Strand Idrætsklub", "Brøndby Strand IK"),
    7123: ("FDC Vista Gelendzhik", "Vista Gelendzhik"),
}

CANDIDATES = ["frem-2026-03-22.fms"]


def find_save(argv):
    if len(argv) > 1:
        return argv[1] if os.path.exists(argv[1]) else None
    base = os.environ.get("FM_SAVES_DIR", os.path.expanduser("~/fm-saves"))
    for name in CANDIDATES:
        for path in (os.path.join(base, "frem", name), os.path.join(base, name), name):
            if os.path.exists(path):
                return path
    return None


def main():
    path = find_save(sys.argv)
    if not path:
        print(f"SKIP: no 2026 Frem save found (looked for {', '.join(CANDIDATES)})")
        return 0

    print(f"save: {path}")
    with Save(path) as s:
        index = R._build_refdata_index(s.mm)[0]
        print(f"clubs indexed: {len(index)}")
        failures = []
        for tid, (long_name, short_name) in sorted(EXPECTED.items()):
            rec = index.get(tid)
            if rec is None:
                failures.append(f"tid {tid}: MISSING (expected {long_name!r}) "
                                f"— the uid gate is dropping club records again")
                continue
            if rec["name"] != long_name or rec["short"] != short_name:
                failures.append(f"tid {tid}: got ({rec['name']!r}, {rec['short']!r}), "
                                f"expected ({long_name!r}, {short_name!r})")
            else:
                print(f"  OK  tid {tid}: {rec['name']!r} / {rec['short']!r}")

        # The fill tier must never DISPLACE a club the primary gate already resolves. These
        # three are the proof case: person records match the club shape (a first name then a
        # surname) and win low tids on file order, so simply raising the uid ceiling renamed
        # them 'Ultee', 'Leemans' and 'Boujemaoui'. If any of these comes back a surname, the
        # fill tier has stopped being gap-only.
        for tid, expected in ((877, "C Cerro Porteño"),
                              (878, "Club Centro Deportivo Municipal"),
                              (879, "Club Sporting Cristal S.A.")):
            rec = index.get(tid)
            got = rec["name"] if rec else None
            if got != expected:
                failures.append(f"tid {tid}: {got!r} — expected {expected!r}; a fill-tier "
                                f"record has displaced a primary one")
            else:
                print(f"  OK  tid {tid} not displaced: {got!r}")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nPASS: every ground-truth club resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
