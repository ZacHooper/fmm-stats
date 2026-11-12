#!/usr/bin/env python3
"""The offline copy covers the whole app: every file the site serves is in site/sw.js's SHELL,
and every file a career's export writes (under api/<career>/) is in its DATA.

The service worker fills its cache from those hand-kept lists, so a new view or JSON payload
left off them works online and breaks offline — and only offline, where nobody is looking. This
fails the moment a list and what it covers disagree, in either direction. Static: needs no store.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.harness import FAIL, PASS, ROOT                                  # noqa: E402

SITE = os.path.join(ROOT, "site")
# Not fetched by the app: agent notes, deploy config and the worker itself.
NOT_CACHED = {"CLAUDE.md", "AGENTS.md", "API.md", ".assetsignore", "sw.js"}
# A career's every-player file is cached separately (from api/<career>/all or all.json).
NOT_IN_DATA = {"all.json"}
EXPORT = os.path.join(ROOT, "scripts", "export_data.py")


def listed(src, name):
    block = re.search(rf"const {name} = \[(.*?)\];", src, re.S).group(1)
    return set(re.findall(r'"([^"]+)"', block))


def main():
    src = open(os.path.join(SITE, "sw.js"), encoding="utf-8").read()
    shell = listed(src, "SHELL") - {"./"}
    data = listed(src, "DATA")
    # The data under api/ is not in git (it is exported locally and served from R2), so it is
    # checked against what export_data.py writes rather than against the disk.
    export = open(EXPORT, encoding="utf-8").read()
    emitted = set(re.findall(r'emit\("([a-z_]+\.json)"', export)) - NOT_IN_DATA
    on_disk = {os.path.relpath(os.path.join(d, f), SITE).replace(os.sep, "/")
               for d, _, fs in os.walk(SITE) for f in fs}
    on_disk = {f for f in on_disk if not f.startswith("api/")} | {"api/careers.json"}
    on_disk -= NOT_CACHED
    problems = [f"site/{f} is not in sw.js SHELL — it won't work offline"
                for f in sorted(on_disk - shell)]
    problems += [f"sw.js SHELL lists {f}, which is not in site/" for f in sorted(shell - on_disk)]
    problems += [f"the export writes {f}, which is not in sw.js DATA — it won't work offline"
                 for f in sorted(emitted - data)]
    problems += [f"sw.js DATA lists {f}, which the export does not write"
                 for f in sorted(data - emitted)]
    for p in problems:
        print(f"  FAIL {p}")
    if not problems:
        print(f"  ok   sw.js SHELL covers all {len(shell)} files in site/, DATA all "
              f"{len(data)} files of a career's export")
    return FAIL if problems else PASS


if __name__ == "__main__":
    sys.exit(main())
