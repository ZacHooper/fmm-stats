#!/usr/bin/env python3
"""Table abstraction engine and savefile table registry."""
from .cities import CITIES_TABLE, CITY, CITY_COUNT, CITY_RECORD, scrape_cities
from .currencies import (
    CURRENCIES_CATALOG,
    CURRENCIES_TABLE,
    CURRENCY_COUNT,
    CURRENCY_HEAD,
    CURRENCY_TAIL,
    scrape_currencies,
)
from .engine import (
    FixedTableDef,
    StringCatalogDef,
    fixed_table_spans,
    string_catalog_spans,
    walk_fixed_table,
    walk_string_catalog,
)
from .officials import OFFICIAL, OFFICIAL_STRIDE, OFFICIALS_TABLE, scrape_officials
from .rounds import (
    ROUND_COUNT,
    ROUND_HEAD,
    ROUND_TRAILER,
    ROUND_TRAILER_WIDTH,
    ROUNDS_CATALOG,
    round_names_map,
    scrape_rounds,
)
from .stadiums import STADIUM_HEAD, STADIUM_HEADER, scrape_stadiums
from .staff import (
    FORMATION_SLOTS,
    HIDDEN_OFFSETS,
    STAFF,
    STAFF_ATTRS,
    STAFF_FIELDS,
    STAFF_FORMATION_SLOTS,
    STAFF_GRID_STRIDE,
    STAFF_HIDDEN_OFFSETS,
    STAFF_STRIDE,
    STAFF_TABLE,
    formation_catalog,
    reputation_tier,
    scrape_staff_attributes,
    staff_table,
    style,
)

# Central Table Registry
TABLES = {
    "rounds": ROUNDS_CATALOG,
    "officials": OFFICIALS_TABLE,
    "cities": CITIES_TABLE,
    "staff": STAFF_TABLE,
    "currencies": CURRENCIES_CATALOG,
}

__all__ = [
    # Engine abstractions
    "FixedTableDef",
    "StringCatalogDef",
    "walk_fixed_table",
    "fixed_table_spans",
    "walk_string_catalog",
    "string_catalog_spans",
    # Registry
    "TABLES",
    # Table instances
    "ROUNDS_CATALOG",
    "OFFICIALS_TABLE",
    "CITIES_TABLE",
    "STAFF_TABLE",
    "CURRENCIES_CATALOG",
    "CURRENCIES_TABLE",
]
