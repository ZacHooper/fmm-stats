#!/usr/bin/env python3
"""
Comment rot: find prose that names something which no longer exists.

A wrong comment is worse than no comment — it sends the next reader (or agent) somewhere that
isn't there, with confidence. This repo leans hard on prose (a quarter of all source lines),
so that failure mode is worth a check rather than a periodic read-through.

Deliberately narrow, because a noisy checker gets ignored. It flags only two things, both
mechanically decidable:

  * a reference to a `.py` file in this repo that does not exist;
  * a backticked call that names a function or class defined nowhere -- Python OR JavaScript,
    because the site half is real code that Python comments legitimately point at.

Note the underscore rule: a private helper is matched with or without its leading
underscore, so a comment saying "characterize()" still resolves to _characterize.

It does NOT flag data files (`fm-frem.duckdb`, `all.json`, `tmp/*.json` are generated,
gitignored or live in R2), prose nouns, or anything under `archive/`. Things it cannot catch
and a human still has to: a comment whose FACTS have drifted — a stated row count, a byte
offset, a claim about which career is the default. For those, see scripts/audit/audit_records.py,
which checks the record layouts against the actual bytes.

Run:  uv run python scripts/audit/audit_comments.py     (exits non-zero on a hit)
"""
import ast
import io
import os
import re
import sys
import tokenize

# Not scanned for stale prose. `archive/` is still INDEXED below (a live comment may
# legitimately point back at an archived script) -- skipping it for both was a false positive.
SKIP_DIRS = {".venv", "venv", ".git", "node_modules", "output", "site-data", "__pycache__",
             "visualizer"}
# "venv" and "visualizer" added 2026-09-16: the checker was walking a vendored,
# GITIGNORED virtualenv (visualizer/backend/venv) and reporting 110 stale references
# from pydantic and typing_extensions, none of them ours. Its own docstring says a noisy
# checker gets ignored, and at 110-to-0 it was already there.
NO_SCAN = {"archive"}
PY_REF = re.compile(r"\b((?:[\w\-]+/)*[\w\-]+\.py)\b")
SYM_REF = re.compile(r"`_?([a-zA-Z_][\w]*)\(\)`|`[\w.]+\.([a-zA-Z_][\w]*)\(\)`")
# JS function/const-arrow declarations, so a Python comment may point at site/js.
JS_DEF = re.compile(r"(?:function\s+([A-Za-z_$][\w$]*)|"
                    r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\()")


def _walk(root):
    for r, d, fs in os.walk(root):
        d[:] = [x for x in d if x not in SKIP_DIRS]
        for fn in fs:
            yield os.path.normpath(os.path.join(r, fn))


def _prose(src):
    """(lineno, text) for every comment and docstring."""
    out = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT:
                out.append((t.start[0], t.string))
    except (tokenize.TokenError, IndentationError):
        pass
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            d = ast.get_docstring(n, clean=False)
            if d:
                out.append((getattr(n, "lineno", 1), d))
    return out


def main():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(root)
    paths = list(_walk("."))
    py = {p for p in paths if p.endswith(".py")}
    py_base = {os.path.basename(p) for p in py}

    symbols = set()
    for p in (x for x in paths if x.endswith(".js")):
        try:
            js = open(p, encoding="utf-8").read()
        except UnicodeDecodeError:
            continue
        for m in JS_DEF.finditer(js):
            symbols.add(m.group(1) or m.group(2))
    for p in py:
        try:
            tree = ast.parse(open(p, encoding="utf-8").read())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.add(n.name)

    bad = []
    for p in sorted(x for x in py if not any(part in NO_SCAN
                                             for part in x.split(os.sep))):
        try:
            src = open(p, encoding="utf-8").read()
        except UnicodeDecodeError:
            continue
        for ln, text in _prose(src):
            for m in PY_REF.finditer(text):
                ref = m.group(1)
                if os.path.normpath(ref) in py or os.path.basename(ref) in py_base:
                    continue
                bad.append((p, ln, f"no such file: {ref}"))
            for m in SYM_REF.finditer(text):
                name = m.group(1) or m.group(2)
                # a private helper may be written either way in prose
                if name and name not in symbols and f"_{name}" not in symbols \
                        and name.lstrip("_") not in symbols:
                    bad.append((p, ln, f"no such symbol: {name}()"))

    for p, ln, why in bad:
        print(f"  {p}:{ln}  {why}")
    print(f"\n{len(bad)} stale reference(s)" if bad else "\nPASS: no stale references")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
