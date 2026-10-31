#!/usr/bin/env python3
"""
Write a modded copy of a save: a recipe (`fmmod/recipes.py`) applied to the Champions Cup's
rule file in the save's data dictionary.

The game copies a competition's rule file into its archive member on the competition's
update day (11 June for the Champions Cup), so the change takes effect for the season that
starts then, and only if the save is dated BEFORE that day (`fmmod/save_patch.py`). The
archive is not touched. The source save is never modified.

    uv run python scripts/mod_save.py ~/fm-saves/frem/frem-2029-04-25.fms final-prize
    uv run python scripts/mod_save.py ~/fm-saves/frem/frem-2029-04-25.fms groups-of-8 --out /tmp/x.fms

After playing the modded save past the update day and saving, check the member took it:

    uv run python scripts/audit/dump_comp_rules.py <later save> --uid 1301394 --tags stgs
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fmmod import recipes as RC                      # noqa: E402
from fmmod.save_patch import patch_rule_file         # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("save")
    ap.add_argument("recipe", choices=sorted(RC.RECIPES))
    ap.add_argument("--out", help="default: <save>-mod-<recipe>.fms beside the source")
    a = ap.parse_args()
    out = a.out or a.save.removesuffix(".fms") + f"-mod-{a.recipe}.fms"
    if os.path.abspath(out) == os.path.abspath(a.save):
        sys.exit("refusing to overwrite the source save")
    r = patch_rule_file(a.save, out, RC.CHAMPIONS_CUP, RC.RECIPES[a.recipe])
    print(f"{out}: {r['rule_file']} {r['old_bytes']} -> {r['new_bytes']} B "
          f"(file shifts {r['shift']:+d} B after it), save {r['size']:,} B")


if __name__ == "__main__":
    main()
