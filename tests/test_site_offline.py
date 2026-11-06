#!/usr/bin/env python3
"""The offline copy covers the whole app: every file the site serves is in site/sw.js's SHELL.

The service worker fills its cache from that hand-kept list, so a new view or JSON payload left
off it works online and breaks offline — and only offline, where nobody is looking. This fails
the moment the list and site/ disagree, in either direction. Static: needs no store.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.harness import FAIL, PASS, ROOT                                  # noqa: E402

SITE = os.path.join(ROOT, "site")
# Not fetched by the app: agent notes, deploy config, the worker itself, and the gitignored
# every-player file (cached separately, from /api/all or api/all.json).
NOT_CACHED = {"CLAUDE.md", "AGENTS.md", "API.md", ".assetsignore", "sw.js", "api/all.json"}
EXPORT = os.path.join(ROOT, "scripts", "export_data.py")


def main():
    src = open(os.path.join(SITE, "sw.js"), encoding="utf-8").read()
    block = re.search(r"const SHELL = \[(.*?)\];", src, re.S).group(1)
    shell = set(re.findall(r'"([^"]+)"', block)) - {"./"}
    # The data under api/ is not in git (it is exported locally and served from R2), so it is
    # checked against what export_data.py emits rather than against the disk.
    emitted = set(re.findall(r'emit\("([a-z_]+\.json)"', open(EXPORT, encoding="utf-8").read()))
    on_disk = {os.path.relpath(os.path.join(d, f), SITE).replace(os.sep, "/")
               for d, _, fs in os.walk(SITE) for f in fs}
    on_disk = {f for f in on_disk if not f.startswith("api/")} | {f"api/{n}" for n in emitted}
    on_disk -= NOT_CACHED
    missing, stale = sorted(on_disk - shell), sorted(shell - on_disk)
    for f in missing:
        print(f"  FAIL site/{f} is not in sw.js SHELL — it won't work offline")
    for f in stale:
        print(f"  FAIL sw.js SHELL lists {f}, which is not in site/")
    if not (missing or stale):
        print(f"  ok   sw.js SHELL covers all {len(shell)} files in site/")
    return FAIL if missing or stale else PASS


if __name__ == "__main__":
    sys.exit(main())
