"""The modelled layers between the landed data and the mart: `stg` and `int`.

    raw (the loader) -> stg (one model per raw table) -> int (joins and rules) -> mart

Every model is DECLARED, not just written as SQL (`Model`): its name, kind, grain (the key
columns that make a row unique), foreign keys, upstream models and SQL. The build order,
the tests (`tests/validate_models.py`) and the docs all read the declaration, the way a
`Record` declaration drives both the parser and `scripts/audit/audit_records.py`.

Only the mart is materialised: stg and int are views, and an int model becomes a table only
for a measured, serious performance reason, given in its `materialised` field. Nothing outside
the build reads upstream of the mart.

`build(con)` creates every model in dependency order; `build(con, targets)` only the named
models and what they read. The compatibility views (`compat.py`) give the models the names
consumers used before they existed, until those consumers move to the mart.

Like the rest of fmstats this reads the store and imports nothing from fmparser: what the
models need to know about the save's layout is in `fmstats/contract.py`.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union

SCHEMAS = ("stg", "int")


@dataclass(frozen=True)
class Model:
    """One model. `name` is `schema.table`; `sql` is the SELECT that defines it, or a function
    of the connection returning it when the SQL is generated from what the store holds (a
    table's columns, the coefficient rows); `upstream` names the models it reads, so the build
    can order them (raw tables need not be listed); `fks` maps a column, or a comma-separated
    list of columns, to what it references, as `schema.table(column, ...)`."""
    name: str
    sql: Union[str, Callable]
    grain: Tuple[str, ...] = ()
    upstream: Tuple[str, ...] = ()
    fks: Dict[str, str] = field(default_factory=dict)
    doc: str = ""
    materialised: Optional[str] = None     # the measured reason, when it is a table

    @property
    def schema(self):
        return self.name.split(".", 1)[0]

    @property
    def kind(self):
        return "table" if self.materialised else "view"

    def select(self, con):
        return self.sql(con) if callable(self.sql) else self.sql


def _registry():
    from . import people, ratings, stg     # noqa: F401  (each module declares its models)
    out = {}
    for m in (*stg.MODELS, *people.MODELS, *ratings.MODELS):
        if m.name in out:
            raise ValueError(f"model {m.name} declared twice")
        if m.schema not in SCHEMAS:
            raise ValueError(f"model {m.name}: schema must be one of {SCHEMAS}")
        out[m.name] = m
    return out


def models() -> Dict[str, Model]:
    """Every declared model, by name."""
    return _registry()


def order(names: Optional[Iterable[str]] = None) -> List[Model]:
    """The named models (default all) and everything they read, upstream first."""
    reg = _registry()
    want = list(reg) if names is None else list(names)
    out, state = [], {}

    def visit(n, path):
        if n not in reg:
            raise KeyError(f"unknown model {n} (via {' -> '.join(path) or 'build'})")
        if state.get(n) == "done":
            return
        if state.get(n) == "open":
            raise ValueError(f"model cycle: {' -> '.join(path + [n])}")
        state[n] = "open"
        for u in reg[n].upstream:
            if u in reg:
                visit(u, path + [n])
        state[n] = "done"
        out.append(reg[n])

    for n in want:
        visit(n, [])
    return out


def build(con, targets: Optional[Iterable[str]] = None, compat_views: bool = True):
    """Create the models (and, unless told not to, the compatibility views over them).
    Returns the models built, in order."""
    for s in SCHEMAS:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")
    built = order(targets)
    for m in built:
        _create(con, m)
    if compat_views:
        from . import compat
        compat.create(con, {m.name for m in built})
    return built


def _create(con, m: Model):
    """(Re)create one model, replacing an object of the other kind under its name."""
    sql = m.select(con)
    if _kind(con, m.name) not in (None, "BASE TABLE" if m.materialised else "VIEW"):
        con.execute(f"DROP {'VIEW' if m.materialised else 'TABLE'} {m.name}")
    con.execute(f"CREATE OR REPLACE {m.kind.upper()} {m.name} AS {sql}")


def _kind(con, name):
    """'BASE TABLE', 'VIEW' or None for `schema.table`."""
    schema, table = name.split(".")
    row = con.execute("SELECT table_type FROM information_schema.tables "
                      "WHERE table_schema = ? AND table_name = ?", [schema, table]).fetchone()
    return row[0] if row else None


# --- checks generated from the declarations (tests/validate_models.py runs them) ----------
def checks(m: Model) -> List[Tuple[str, str]]:
    """(description, SQL returning the number of offending rows) for one model: its grain is
    unique and never NULL, and each foreign key resolves."""
    out = []
    if m.grain:
        g = ", ".join(m.grain)
        out.append((f"{m.name}: grain ({g}) is unique",
                    f"SELECT count(*) FROM (SELECT {g} FROM {m.name} "
                    f"GROUP BY ALL HAVING count(*) > 1)"))
        nulls = " OR ".join(f"{c} IS NULL" for c in m.grain)
        out.append((f"{m.name}: grain ({g}) is never NULL",
                    f"SELECT count(*) FROM {m.name} WHERE {nulls}"))
    for cols, ref in m.fks.items():
        target, tcols = ref.rstrip(")").split("(")
        mine = [c.strip() for c in cols.split(",")]
        theirs = [c.strip() for c in tcols.split(",")]
        on = " AND ".join(f"t.{b} = x.{a}" for a, b in zip(mine, theirs))
        present = " AND ".join(f"x.{a} IS NOT NULL" for a in mine)
        out.append((f"{m.name}({cols}) -> {ref} resolves",
                    f"SELECT count(*) FROM {m.name} x WHERE {present} "
                    f"AND NOT EXISTS (SELECT 1 FROM {target} t WHERE {on})"))
    return out
