#!/usr/bin/env python3
"""Check that every doc's references still point at something.

    uv run python scripts/check_docs.py              # every .md and .html doc in the repo
    uv run python scripts/check_docs.py README.md docs/TODO.md

Two kinds of reference are checked, in every `.md` and `.html` doc:

- **A cited repo path**: text that names a path under one of the repo's top-level folders
  (`fmparser/…`, `scripts/…`, `tests/…`, `fmstats/…`, `site/…`, `docs/…`, …), in prose, inline
  code or a code block. It must exist from the repo root, or from the doc's own folder.
  A path written as a template (`docs/parser/<table>.md`, `output/{label}/`, `…`) is skipped;
  a glob (`fmstats/models/_*.yml`) must match something.
- **A relative link**: a Markdown `[text](target)` / `[ref]: target`, or an HTML `href`/`src`.
  The file must exist, and an `#anchor` must name a heading (GitHub's slug) or an `id`/`name`
  in the target. Links with a scheme (`https:`, `mailto:`) are not checked.

The docs are the files git sees (tracked, plus untracked files that are not ignored), so a
gitignored file such as your own `CAREER.md` is neither scanned nor counted as present, and the
result is the same on your machine and in CI. Outside a git checkout it walks the tree,
skipping `.venv`, `.git`, `output/` and `site/api/`.

Lines between `<!-- check-docs: off -->` and `<!-- check-docs: on -->` are skipped, for a doc
that quotes this script's own report.

ALLOWLIST holds the paths that are deliberately absent (gitignored inputs and outputs);
a reference to one, or to anything under one, passes.

Each failure prints as `file:line -> target (kind)`, the kind being `missing path`,
`missing file` or `missing anchor`. Exit 0 when nothing is missing, 1 otherwise.
"""
import argparse
import glob
import html
import os
import re
import subprocess
import sys
from collections import Counter
from functools import lru_cache
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Folders never scanned when walking the tree (git already leaves them out).
SKIP_DIRS = {".venv", ".git", "output", "site/api", "node_modules", "fmstats/target",
             "fmstats/dbt_packages", "fmstats/logs"}

# Deliberately absent: gitignored by design. An entry ending in "/" covers everything under it.
ALLOWLIST = (
    "fmm.toml",
    "CAREER.md",
    "site/api/",
    "output/",
    "fmstats/known_answers/",
    "fmstats/target/",
    "fmstats/logs/",
    "fmstats/dbt_packages/",
    "site-data/",
    "state/",
    "backups/",
    "scratch/",
    ".oracle/",
    ".wrangler/",
)

# Top-level folders whose paths count as a citation when they appear in a doc's text.
PATH_ROOTS = ("fmparser", "fmstats", "scripts", "tests", "site", "site-worker", "docs",
              "seeds", ".claude", ".github")
PATH_RE = re.compile(
    r"(?<![\w./\-~$@])(?:%s)/[\w.\-/*]*" % "|".join(re.escape(r) for r in PATH_ROOTS))
# A character straight after a path that makes it a template, not a real path.
TEMPLATE_NEXT = ("<", "{", "…", "[", "$")

MD_LINK_RE = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*<?([^)\s>]*)>?(?:\s+\"[^\"]*\")?\s*\)")
MD_REF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)")
HTML_LINK_RE = re.compile(r"""\b(?:href|src)\s*=\s*(["'])(.*?)\1""", re.I)
HTML_ID_RE = re.compile(r"""\b(?:id|name)\s*=\s*(["'])(.*?)\1""", re.I)
TAG_RE = re.compile(r"<[^>]*>")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1")
OFF_MARK, ON_MARK = "<!-- check-docs: off -->", "<!-- check-docs: on -->"
GITHUB_LINE_ANCHOR = re.compile(r"^L\d+(-L\d+)?$")


def git_files():
    """Files git sees (tracked + untracked-not-ignored), relative to ROOT, or None."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return {p for p in out.decode().split("\0") if p and os.path.exists(os.path.join(ROOT, p))}


def walk_files():
    files = set()
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel = os.path.relpath(dirpath, ROOT).replace(os.sep, "/")
        rel = "" if rel == "." else rel + "/"
        dirnames[:] = [d for d in dirnames if rel + d not in SKIP_DIRS]
        files.update(rel + f for f in filenames)
    return files


class Repo:
    """The set of files (and the folders that hold them) a reference may point at."""

    def __init__(self, files):
        self.files = files
        self.dirs = {""}
        for f in files:
            parts = f.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                self.dirs.add("/".join(parts[:i]))

    def exists(self, rel):
        rel = rel.rstrip("/")
        return rel in self.files or rel in self.dirs

    def is_file(self, rel):
        return rel in self.files

    def glob(self, pattern):
        rx = re.compile("[^/]*".join(re.escape(p) for p in pattern.rstrip("/").split("*")))
        return any(rx.fullmatch(p) for p in self.files | self.dirs)


def allowlisted(rel):
    for a in ALLOWLIST:
        if a.endswith("/"):
            if rel == a.rstrip("/") or rel.startswith(a):
                return True
        elif rel == a:
            return True
    return False


def normalise(path):
    """A repo-relative path with `.`/`..` folded, or None when it climbs out of the repo."""
    parts = []
    for p in path.split("/"):
        if p in ("", "."):
            continue
        if p == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(p)
    return "/".join(parts)


# ---- anchors -------------------------------------------------------------------------------

def github_slug(text):
    """The anchor GitHub gives a Markdown heading with this text."""
    text = INLINE_CODE_RE.sub(lambda m: m.group(2), text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)   # links -> their text
    text = TAG_RE.sub("", text)
    text = html.unescape(text).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


@lru_cache(maxsize=None)
def anchors_of(abspath):
    try:
        with open(abspath, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return set()
    found = {m.group(2) for m in HTML_ID_RE.finditer(text)}
    if abspath.endswith(".md"):
        seen = Counter()
        fence = None
        for line in text.splitlines():
            m = FENCE_RE.match(line)
            if m:
                if fence is None:
                    fence = m.group(1)[0]
                elif m.group(1)[0] == fence:
                    fence = None
                continue
            if fence:
                continue
            h = HEADING_RE.match(line)
            if h:
                slug = github_slug(h.group(2))
                n = seen[slug]
                seen[slug] += 1
                found.add(slug if n == 0 else f"{slug}-{n}")
    return found


# ---- scanning ------------------------------------------------------------------------------

def strip_inline_code(line):
    return INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)


def cited_paths(text):
    """(path, is_glob) for each repo path named in a line of plain text."""
    for m in PATH_RE.finditer(text):
        path = m.group(0)
        nxt = text[m.end():m.end() + 1]
        if nxt in TEMPLATE_NEXT or "..." in path or path.endswith(("-", "*.")):
            continue
        path = re.sub(r"(\.\w+)\*+$", r"\1", path)        # **bold** around a path
        path = path.rstrip(".,;")
        if not path or "//" in path:
            continue
        yield path, "*" in path


def path_variants(path):
    """A cited path, plus the module file when it is written `scripts/x.attr` (a Python name)."""
    yield path
    stem, dot, attr = path.rpartition(".")
    if dot and "/" not in attr and attr.isidentifier() and attr not in KNOWN_EXTS:
        yield stem + ".py"


KNOWN_EXTS = {"py", "md", "html", "sql", "yml", "yaml", "csv", "json", "js", "css", "toml",
              "txt", "png", "jpg", "svg", "sh", "gz", "fms", "duckdb", "jsonc", "lock"}


def links_in(path, lines):
    """(line number, target) for each link in a doc."""
    is_md = path.endswith(".md")
    fence = None
    for n, line in enumerate(lines, 1):
        if is_md:
            m = FENCE_RE.match(line)
            if m:
                if fence is None:
                    fence = m.group(1)[0]
                elif m.group(1)[0] == fence:
                    fence = None
                continue
            if fence:
                continue
            plain = strip_inline_code(line)
            for m in MD_LINK_RE.finditer(plain):
                yield n, m.group(1)
            m = MD_REF_RE.match(plain)
            if m:
                yield n, m.group(1)
        for m in HTML_LINK_RE.finditer(line if not is_md else strip_inline_code(line)):
            yield n, html.unescape(m.group(2))


def text_lines(path, lines):
    """Each line as text to search for cited paths: HTML loses its tags and entities."""
    if path.endswith(".html"):
        in_block = None
        for n, line in enumerate(lines, 1):
            low = line.lower()
            if in_block:
                if f"</{in_block}" in low:
                    in_block = None
                continue
            m = re.search(r"<(script|style)\b", low)
            if m and f"</{m.group(1)}" not in low[m.end():]:
                in_block = m.group(1)
                continue
            line = HTML_LINK_RE.sub(" ", line)       # links are checked as links
            yield n, html.unescape(TAG_RE.sub(" ", line))
    else:
        for n, line in enumerate(lines, 1):
            # A Markdown link's target is checked as a link, not again as a citation.
            yield n, MD_LINK_RE.sub(lambda m: " " * len(m.group(0)), line) if "](" in line else line


def check_file(doc, repo):
    """Failures in one doc, as (line, target, kind)."""
    with open(os.path.join(ROOT, doc), encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    # Lines between `<!-- check-docs: off -->` and `<!-- check-docs: on -->` are not checked
    # (a quoted report of broken references, say). They are blanked so numbering holds.
    off = False
    for i, line in enumerate(lines):
        if OFF_MARK in line:
            off = True
        elif ON_MARK in line:
            off = False
        elif off:
            lines[i] = ""
    here = os.path.dirname(doc)
    failures = []
    seen = set()

    def fail(n, target, kind):
        if (n, target, kind) not in seen:
            seen.add((n, target, kind))
            failures.append((n, target, kind))

    for n, line in text_lines(doc, lines):
        for path, is_glob in cited_paths(line):
            candidates = []
            for p in path_variants(path):
                candidates.append(normalise(p))
                if here:
                    candidates.append(normalise(f"{here}/{p}"))
            candidates = [c for c in candidates if c is not None]
            if any(allowlisted(c) for c in candidates):
                continue
            check = repo.glob if is_glob else repo.exists
            if not any(check(c) for c in candidates):
                fail(n, path, "missing path")

    for n, target in links_in(doc, lines):
        target = target.strip()
        if not target or SCHEME_RE.match(target) or target.startswith(("//", "/")):
            continue
        file_part, _, anchor = target.partition("#")
        file_part = unquote(file_part.split("?", 1)[0])
        if file_part:
            rel = normalise(f"{here}/{file_part}" if here else file_part)
            if rel is None:
                fail(n, target, "missing file")
                continue
            if allowlisted(rel):
                continue
            if not repo.exists(rel):
                fail(n, target, "missing file")
                continue
        else:
            rel = doc
        if anchor and repo.is_file(rel):
            if rel.endswith((".md", ".html", ".htm")):
                if unquote(anchor) not in anchors_of(os.path.join(ROOT, rel)):
                    fail(n, target, "missing anchor")
            elif not GITHUB_LINE_ANCHOR.match(anchor):
                fail(n, target, "missing anchor")
    return failures


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docs", nargs="*", help="docs to check (default: every .md/.html doc)")
    ap.add_argument("--summary", action="store_true",
                    help="after the list, print counts by doc and by kind")
    args = ap.parse_args(argv)

    files = git_files()
    if files is None:
        files = walk_files()
    repo = Repo(files)

    if args.docs:
        docs = [os.path.relpath(os.path.abspath(d), ROOT).replace(os.sep, "/") for d in args.docs]
    else:
        docs = sorted(f for f in files if f.endswith((".md", ".html"))
                      and not any(f == d or f.startswith(d + "/") for d in SKIP_DIRS))

    total = []
    for doc in docs:
        for n, target, kind in check_file(doc, repo):
            total.append((doc, n, target, kind))
            print(f"{doc}:{n} -> {target} ({kind})")

    if args.summary and total:
        print("\nby doc:")
        for doc, c in Counter(d for d, *_ in total).most_common():
            print(f"  {c:4d}  {doc}")
        print("by kind:")
        for kind, c in Counter(k for *_, k in total).most_common():
            print(f"  {c:4d}  {kind}")
    print(f"{len(total)} broken reference(s) in {len({d for d, *_ in total})} of "
          f"{len(docs)} doc(s)", file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
