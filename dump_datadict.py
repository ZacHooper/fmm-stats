#!/usr/bin/env python3
"""
Materialize the save's tagged data dictionary (~17-20.8 MB) to a local JSON store.

    python3 dump_datadict.py path/to/save.fms [--label 2022-end] [--out output]

Writes output/<label>/datadict/:
    <entity>.json    one file per entity type (comp, fxds, stdt, ...): every id-headed
                     record of that type at any nesting depth, fully nested & lossless
    _stream.json     the complete ordered item stream (records + raw blobs) — the lossless
                     master; reconstructs the region's data without re-reading the save
    _coverage.json   byte-accounting proof (tagged / raw / padding; unaccounted == 0)
    _index.json      entity -> file + record count

The label defaults to the same <year>-<period> extract.py derives (so the dump lands in
the same output/<label>/ bundle); override with --label.
"""
import argparse
import os

from fmparser.save import Save
from fmparser import datadict as D
from fmparser import matches as M
import extract


def main():
    ap = argparse.ArgumentParser(description="Dump the tagged data dictionary to JSON.")
    ap.add_argument("save", help="path to the .fms save file")
    ap.add_argument("--label", help="output label (default: auto <year>-<period>)")
    ap.add_argument("--out", default="output", help="output root (default: output/)")
    args = ap.parse_args()

    s = Save(args.save)
    mm = s.mm
    if args.label:
        label = args.label
    else:
        label, _ = extract.auto_label(M.extract_season(mm))
    dest = os.path.join(args.out, label, "datadict")

    cov = D.dump_json(mm, dest)
    print(f"datadict -> {dest}/")
    print(f"  {cov['entity_count']} entities  {cov['record_count']} records  "
          f"tagged {cov['tagged_pct']}%  raw {cov['raw_pct']}%  "
          f"padding {cov['padding_bytes']}B  unaccounted {cov['unaccounted_bytes']}B")
    s.close()


if __name__ == "__main__":
    main()
