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
from .names import (
    FIRST_NAMES_TABLE,
    NAME_ID_ENTRY,
    NAME_ID_STRIDE,
    NICKNAMES_TABLE,
    SURNAMES_TABLE,
    chain_id_tables,
    discover_id_tables,
    locate_first_names,
    locate_name_tables,
    locate_nicknames,
    locate_surnames,
    walk_browse,
    walk_browse_bounds,
)
from .officials import OFFICIAL, OFFICIAL_STRIDE, OFFICIALS_TABLE, scrape_officials
from .player_attributes import (
    PLAYER_ATTRIBUTES_TABLE,
    locate_player_attributes,
    scrape_player_attributes,
)
from .rounds import (
    ROUND_COUNT,
    ROUND_HEAD,
    ROUND_TRAILER,
    ROUND_TRAILER_WIDTH,
    ROUNDS_CATALOG,
    round_names_map,
    scrape_rounds,
)
from .stadiums import (
    STADIUM_HEAD,
    STADIUM_HEADER,
    STADIUMS_CATALOG,
    locate_stadiums,
    scrape_stadiums,
)
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
    "stadiums": STADIUMS_CATALOG,
    "surnames": SURNAMES_TABLE,
    "first_names": FIRST_NAMES_TABLE,
    "nicknames": NICKNAMES_TABLE,
    "player_attributes": PLAYER_ATTRIBUTES_TABLE,
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
    "STADIUMS_CATALOG",
    "SURNAMES_TABLE",
    "FIRST_NAMES_TABLE",
    "NICKNAMES_TABLE",
    "PLAYER_ATTRIBUTES_TABLE",
]
