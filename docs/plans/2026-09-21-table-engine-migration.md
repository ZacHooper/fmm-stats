# Table Engine Migration Plan

> **Goal:** Consolidate static and framed savefile tables into the declarative `fmparser/tables.py` engine (`FixedTableDef` and `StringCatalogDef`), unifying record reading, span generation for coverage audits, and ID mappings while maintaining zero regression against baseline outputs.

**Architecture:**
- Declarative schemas live in `fmparser/schemas/`.
- Registered table definitions live in `fmparser/tables.py`.
- `TableDef` subclasses provide `.scrape(mm)`, `.spans(mm)`, and `.id_map(mm)`.
- Existing module functions (e.g. `places.scrape_cities`, `staff.scrape_staff_attributes`, `lookups.scrape_currencies`) become thin shims delegating to `tables.py`.

---

## Batch 1: Immediate Candidates (`cities`, `staff_attributes`, `currencies`)

### Task 1: Add `.scrape()`, `.spans()`, and `.id_map()` to `FixedTableDef` and `StringCatalogDef`
- **Files:** `fmparser/tables.py`, `tests/test_tables.py`
- Add unified methods on `FixedTableDef` and `StringCatalogDef`:
  - `scrape(mm) -> List[Dict[str, Any]]`
  - `spans(mm, include_count_header=True) -> List[Tuple[int, int]]`
  - `id_map(mm, key_field="id") -> Dict[Any, Dict[str, Any]]`
- Add synthetic unit tests in `tests/test_tables.py`.

### Task 2: Migrate `cities` to `FixedTableDef`
- **Files:** `fmparser/tables.py`, `fmparser/places.py`, `fmparser/schemas/places.py`
- **Schema:** `CITY` (20 bytes: `id u16`, `nation_id u16`, `state_id u16`, `latitude f32`, `longitude f32`).
- **Locator:** Anchor on city grid or declared count `[8x 0xFF][u16 count = 10,956]` at `start - 2`.
- **Post-processor:** Convert valid coordinates, round float32 to 6 decimals, set None if invalid.
- Verify `places.scrape_cities(mm)` delegates cleanly to `CITIES_TABLE.id_map(mm)`.

### Task 3: Migrate `staff_attributes` to `FixedTableDef`
- **Files:** `fmparser/tables.py`, `fmparser/staff.py`, `fmparser/schemas/staff.py`
- **Schema:** `STAFF` (39 bytes).
- **Locator:** Reuses `staff.staff_table(mm)` returning `(base, count)`.
- **Post-processor:** Attaches derived `style`, `reputation_tier`, and formation dictionary.
- Verify `staff.scrape_staff_attributes(mm, id2s)` uses `STAFF_TABLE.id_map(mm)`.

### Task 4: Migrate `currencies` to `StringCatalogDef`
- **Files:** `fmparser/tables.py`, `fmparser/lookups.py`, `fmparser/schemas/lookups.py` (or `schemas/currencies.py`)
- **Schema:** `CURRENCY_HEAD` (2B `uid u16`), `CURRENCY_TAIL` (4B `exchange_rate f32`).
- **Locator:** Declared count `u16` at `start - 2` preceded by 10x 0xFF filler.
- Verify `lookups.scrape_currencies(mm)` delegates to `CURRENCIES_TABLE.id_map(mm, key_field="uid")`.

### Task 5: Regression Verification
- Run `uv run python scripts/run_tests.py -u` (fast unit tests).
- Run `uv run python scripts/run_tests.py` (full suite).
- Run `uv run python scripts/assert_identical.py` (verify 88/88 baseline outputs remain 100% byte-identical).

---

## Batch 2: Grids & Catalogs (`stadiums`, `name_id_tables`, `player_attributes`)
- **`stadiums`**: `StringCatalogDef` (18B `STADIUM_HEAD` + name + `\0`).
- **`name_id_tables`**: Three chained `FixedTableDef`s (16B stride; 32,148 surnames, 19,128 first names, 9,480 nicknames).
- **`player_attributes`**: `FixedTableDef` (78B stride; 26,505 records).

---

## Batch 3: Multi-String Catalog Extension (`languages`, `nations`)
- Extend `StringCatalogDef` to support multiple consecutive length-prefixed strings:
  - `languages`: `LANGUAGE_HEAD` (6B) + `name` + `other_name` + `LANGUAGE_TAIL` (3B).
  - `nations`: `NATION_HEAD` (6B) + `name` + `nationality` + `code` + `NATION_TAIL` (6B).
