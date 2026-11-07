#!/usr/bin/env python3
"""Unit tests for scripts/check_docs.py over a small throwaway repo (line numbers are 1-based)."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import check_docs  # noqa: E402

FILES = {
    "README.md": "\n".join([
        "# Top",
        "## Play style (set in `fmm.toml`)",
        "## Top",
        "Run `scripts/real.py` and scripts/gone.py, then read docs/a.md.",
        "[ok](docs/a.md#section-one) [bad](docs/a.md#nope) [gone](docs/b.md)",
        "[self](#play-style-set-in-fmmtoml) [dup](#top-1) [x](#missing)",
        "Templates pass: docs/parser/<table>.md, output/{label}/, fmm.toml, site/api/x.json.",
        "A glob fmparser/tables/*.py matches; tests/*.nope does not.",
        "A name scripts/real.main and a link [web](https://example.com/docs/x).",
        "```",
        "[not a link](docs/nowhere.md) but scripts/fenced_gone.py is a citation",
        "```",
        "Bold **scripts/real.py** and a line anchor [l](scripts/real.py#L10).",
        "<!-- check-docs: off -->",
        "scripts/quoted_gone.py [q](docs/quoted.md)",
        "<!-- check-docs: on -->",
        "scripts/after_gone.py",
    ]),
    "docs/a.md": "## Section one\n<a id=\"custom\"></a>\n[up](../README.md#top) [c](#custom)\n"
                 "[wrong](README.md)\n",
    "docs/p.html": '<h2 id="map">Map</h2>\n<a href="#map">m</a> <a href="#gone">g</a>\n'
                   "<p><code>scripts/real.py</code> and <code>docs/missing.md</code></p>\n"
                   "<p>docs/parser/&lt;table&gt;.md</p>\n",
    "scripts/real.py": "",
    "fmparser/tables/t.py": "",
}


def main():
    with tempfile.TemporaryDirectory() as tmp:
        for rel, text in FILES.items():
            os.makedirs(os.path.dirname(os.path.join(tmp, rel)) or tmp, exist_ok=True)
            with open(os.path.join(tmp, rel), "w") as f:
                f.write(text)
        check_docs.ROOT = tmp
        check_docs.anchors_of.cache_clear()
        repo = check_docs.Repo(check_docs.walk_files())
        got = {doc: sorted(check_docs.check_file(doc, repo))
               for doc in ("README.md", "docs/a.md", "docs/p.html")}

    want = {
        "README.md": sorted([
            (4, "scripts/gone.py", "missing path"),
            (5, "docs/a.md#nope", "missing anchor"),
            (5, "docs/b.md", "missing file"),
            (6, "#missing", "missing anchor"),
            (8, "tests/*.nope", "missing path"),
            (11, "scripts/fenced_gone.py", "missing path"),
            (17, "scripts/after_gone.py", "missing path"),
        ]),
        "docs/a.md": [(4, "README.md", "missing file")],
        "docs/p.html": sorted([
            (2, "#gone", "missing anchor"),
            (3, "docs/missing.md", "missing path"),
        ]),
    }
    failed = 0
    for doc in want:
        if got[doc] != want[doc]:
            failed = 1
            print(f"FAIL {doc}\n  got:  {got[doc]}\n  want: {want[doc]}")
    for text, slug in [("Play style (set in `fmm.toml`)", "play-style-set-in-fmmtoml"),
                       ("The [link](x.md) & more", "the-link--more"),
                       ("fact_player_match", "fact_player_match")]:
        if check_docs.github_slug(text) != slug:
            failed = 1
            print(f"FAIL slug {text!r} -> {check_docs.github_slug(text)!r}, want {slug!r}")
    print("FAIL" if failed else "PASS", "check_docs")
    return failed


if __name__ == "__main__":
    sys.exit(main())
