#!/usr/bin/env python3
"""The savefile table registry: every table definition, by name (`TABLES`), and where each
sits in a save (`table_spans`, `first_record`). The engine is `fmparser/core/table.py`."""
from typing import Any, Dict, List, Optional, Tuple

from ..core import LinkedTableDef, TaggedTableDef
from .save_header import FMM22, FMM27, save_format
from .cities import CITIES_TABLE, CITY, CITY_RECORD, cities_table_spans, scrape_cities
from .clubs import CLUB_TABLE, CLUB_TABLE_FMM27, locate_clubs, scrape_clubs
from .history import HISTORY_TABLE, locate_history, scrape_history
from .player_progress import (PLAYER_PROGRESS_TABLE, locate_player_progress,
                              scrape_player_progress)
from .training import (LOAN_STATUS, TRAINING_TABLE, locate_training, scrape_unknown_39,
                       scrape_training, training_table_spans)
from .player_lists import (PLAYER_LISTS_TABLE, PLAYER_LISTS_TABLE_FMM27,
                           PLAYER_LIST_TRAILERS_TABLE,
                           locate_player_lists, player_lists_table_spans,
                           scrape_player_lists)
from .club_records import (CLUB_RECORDS_TABLE, club_records_table_spans, locate_club_records,
                           scrape_club_records)
from .competitions import COMP_TABLE, COMP_TABLE_FMM27, comp_refs, locate_competitions, scrape_competitions
from .contracts import (
    CONTRACT,
    CONTRACT_DETAIL,
    CONTRACT_RECORD,
    CONTRACT_STRIDE,
    CONTRACT_TABLE,
    contracts_table_spans,
    locate_contracts,
    scrape_contracts,
)
from .comp_rules import (
    COMP_RULES_TABLE,
    COMP_RULES_TABLE_FMM27,
    HEADER as COMP_RULES_HEADER,
    competition_rounds,
    locate_comp_rules,
    scrape as scrape_comp_rules,
    stage_rows as comp_rule_stage_rows,
)
from .rule_files import (
    RULE_FILES_TABLE,
    RULE_FILES_TABLE_FMM27,
    locate_rule_files,
    team_counts as rule_file_team_counts,
)
from .currencies import (
    CURRENCIES_TABLE,
    CURRENCY_HEAD,
    CURRENCY_TAIL,
    scrape_currencies,
)
from .fixtures import (
    DAY_BASE as FIXTURE_DAY_BASE,
    DAY_MASK as FIXTURE_DAY_MASK,
    FIXTURE,
    FIXTURES_TABLE,
    FIXTURES_TABLE_FMM27,
    MEMBER as FIXTURES_MEMBER,
    MEMBER_HEADER as FIXTURES_MEMBER_HEADER,
    NO_ROUND as FIXTURE_NO_ROUND,
    OPENER as FIXTURE_OPENER,
    STRIDE as FIXTURE_STRIDE,
    fixtures as extract_world_fixtures,
    locate_fixtures,
    read_fixture,
    scrape as scrape_fixtures,
    segments as fixture_segments,
    summary as fixtures_summary,
)
from .comp_stages import (
    COMP_STAGES_TABLE,
    HEADER as COMP_STAGES_HEADER,
    HEADER_STRIDE as COMP_STAGES_HEADER_STRIDE,
    STAGE as COMP_STAGE,
    STRIDE as COMP_STAGE_STRIDE,
    header as comp_stages_header,
    locate_comp_stages,
    read_stage as read_comp_stage,
    scrape as scrape_comp_stages,
    stages as extract_comp_stages,
)
from .comp_honours import (
    COMP_HONOURS_TABLE,
    HONOUR as COMP_HONOUR,
    OPENER as COMP_HONOUR_OPENER,
    STRIDE as COMP_HONOUR_STRIDE,
    honours as extract_comp_honours,
    locate_comp_honours,
    read_honour as read_comp_honour,
    scrape as scrape_comp_honours,
)
from .languages import (
    LANGUAGES_TABLE,
    LANGUAGE_HEAD,
    LANGUAGE_TAIL,
    languages_table_spans,
    locate_languages,
    scrape_languages,
)
from .match_slots import (
    MATCH_SLOTS_TABLE,
    NO_CLUB as MATCH_SLOT_NO_CLUB,
    SLOT as MATCH_SLOT,
    STRIDE as MATCH_SLOT_STRIDE,
    locate_match_slots,
    match_slots_table_spans,
    scrape as scrape_match_slots,
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
from .nations import (
    NATIONS_TABLE_FMM27,
    NATION_HEAD,
    NATION_TAIL,
    NATIONS_TABLE,
    locate_nations,
    nations_table_spans,
    scrape_nations,
)
from .officials import OFFICIAL, OFFICIAL_STRIDE, OFFICIALS_TABLE, scrape_officials
from .person_info import (
    INFO_HEAD,
    INFO_LAYOUT,
    NO_CLUB,
    PERSONALITY,
    PERSON_FIELDS,
    PERSON_INFO,
    PERSON_INFO_TABLE,
    PERSON_INFO_TABLE_FMM27,
    locate_person_info,
    person_info_table_spans,
    scrape_person_info,
    scrape_players,
)
from .player_attributes import (
    PLAYER_ATTRIBUTES_TABLE,
    PLAYER_ATTRIBUTES_TABLE_FMM27,
    locate_player_attributes,
    record_for,
    scrape_player_attributes,
)
from .matches import (
    EVENT_TYPE,
    MATCHES_TABLE,
    MATCHES_TABLE_FMM27,
    MatchTableError,
    check_against_fixtures,
    locate_matches,
    matches_table_spans,
    scrape_matches,
)
from .rounds import (
    ROUND_HEAD,
    ROUND_TRAILER,
    ROUND_TRAILER_WIDTH,
    ROUNDS_TABLE,
    ROUNDS_TABLE_FMM27,
    round_names_map,
    scrape_rounds,
)
from .stadiums import (
    STADIUM_HEAD,
    STADIUM_HEADER,
    STADIUMS_TABLE,
    STADIUMS_TABLE_FMM27,
    locate_stadiums,
    scrape_stadiums,
)
from .staff_roles import COACHES_TABLE, PHYSIOS_TABLE, SCOUTS_TABLE, scrape_staff_roles
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
    style,
)

TABLES = {
    "cities": CITIES_TABLE,
    "clubs": CLUB_TABLE,
    "competitions": COMP_TABLE,
    "history": HISTORY_TABLE,
    "club_records": CLUB_RECORDS_TABLE,
    "player_lists": PLAYER_LISTS_TABLE,
    "player_progress": PLAYER_PROGRESS_TABLE,
    "training": TRAINING_TABLE,
    "player_list_trailers": PLAYER_LIST_TRAILERS_TABLE,
    "comp_honours": COMP_HONOURS_TABLE,
    "comp_rules": COMP_RULES_TABLE,
    "rule_files": RULE_FILES_TABLE,
    "comp_stages": COMP_STAGES_TABLE,
    "contracts": CONTRACT_TABLE,
    "currencies": CURRENCIES_TABLE,
    "first_names": FIRST_NAMES_TABLE,
    "fixtures": FIXTURES_TABLE,
    "languages": LANGUAGES_TABLE,
    "match_officials": OFFICIALS_TABLE,
    "match_slots": MATCH_SLOTS_TABLE,
    "matches": MATCHES_TABLE,
    "nations": NATIONS_TABLE,
    "nicknames": NICKNAMES_TABLE,
    "person_info": PERSON_INFO_TABLE,
    "player_attributes": PLAYER_ATTRIBUTES_TABLE,
    "round_names": ROUNDS_TABLE,
    "stadiums": STADIUMS_TABLE,
    "staff": STAFF_TABLE,
    "coaches": COACHES_TABLE,
    "scouts": SCOUTS_TABLE,
    "physios": PHYSIOS_TABLE,
    "surnames": SURNAMES_TABLE,
}

# The declarations each game version reads with. A table with no declaration of its own for
# a version is read with FMM22's: that is a claim to test, not a decode (the FMM27 plan
# lists which tables are confirmed).
TABLES_BY_FORMAT = {
    FMM22: TABLES,
    FMM27: {**TABLES, "person_info": PERSON_INFO_TABLE_FMM27,
            "player_attributes": PLAYER_ATTRIBUTES_TABLE_FMM27,
            "round_names": ROUNDS_TABLE_FMM27, "clubs": CLUB_TABLE_FMM27,
            "competitions": COMP_TABLE_FMM27, "nations": NATIONS_TABLE_FMM27,
            "stadiums": STADIUMS_TABLE_FMM27, "rule_files": RULE_FILES_TABLE_FMM27,
            "player_lists": PLAYER_LISTS_TABLE_FMM27, "comp_rules": COMP_RULES_TABLE_FMM27,
            "fixtures": FIXTURES_TABLE_FMM27, "matches": MATCHES_TABLE_FMM27},
}


def tables_for(mm: Any) -> Dict[str, Any]:
    """The registry for this save's declared format; FMM22's for a version with none."""
    return TABLES_BY_FORMAT.get(save_format(mm), TABLES)



def table_spans(mm: Any, name: str) -> List[Tuple[int, int]]:
    """[(start, end)]: the bytes a registered table covers, framing included. A module's own
    `<name>_table_spans` is used where it has one (it adds framing the definition does not
    own: person_info's header byte after its count); a tagged table's blocks carry their u32
    count."""
    own = globals().get(f"{name}_table_spans")
    if own is not None:
        return own(mm)
    table = tables_for(mm)[name]
    if isinstance(table, TaggedTableDef):
        return [(b.start - 4, b.end) for b in table.blocks(mm)]
    return table.spans(mm)


def first_record(mm: Any, name: str) -> Optional[int]:
    """The offset of a registered table's first record, behind its frame; None when the
    table is not located (an empty match table)."""
    table = tables_for(mm)[name]
    if isinstance(table, LinkedTableDef):
        loc = table.locator(mm)
        return loc[0] if loc else None
    if isinstance(table, TaggedTableDef):
        locs = table.locator(mm) or []
        return locs[0][0] if locs else None
    runs = table.runs(mm)
    return runs[0][0] if runs else None


__all__ = [
    # Engine
    "TABLES",
    "TABLES_BY_FORMAT",
    "tables_for",
    "first_record",
    "table_spans",
    # History
    "HISTORY_TABLE",
    "locate_history",
    "scrape_history",
    # Player progress
    "PLAYER_PROGRESS_TABLE",
    "locate_player_progress",
    "scrape_player_progress",
    # Training
    "TRAINING_TABLE",
    "locate_training",
    "scrape_training",
    "training_table_spans",
    # Player lists
    "PLAYER_LISTS_TABLE",
    "PLAYER_LIST_TRAILERS_TABLE",
    "locate_player_lists",
    "player_lists_table_spans",
    "scrape_player_lists",
    # Club records
    "CLUB_RECORDS_TABLE",
    "club_records_table_spans",
    "locate_club_records",
    "scrape_club_records",
    # Cities
    "CITIES_TABLE",
    "CITY",
    "CITY_RECORD",
    "scrape_cities",
    # Clubs and competitions
    "CLUB_TABLE",
    "COMP_TABLE",
    "comp_refs",
    "locate_clubs",
    "locate_competitions",
    "scrape_clubs",
    "scrape_competitions",
    # Competition rules (archive comp_<uid>.dat)
    "COMP_RULES_HEADER",
    "COMP_RULES_TABLE",
    "comp_rule_stage_rows",
    "competition_rounds",
    "locate_comp_rules",
    "scrape_comp_rules",
    # Rule files (the tagged data dictionary)
    "RULE_FILES_TABLE",
    "locate_rule_files",
    "rule_file_team_counts",
    # Contracts
    "CONTRACT",
    "CONTRACT_DETAIL",
    "CONTRACT_RECORD",
    "CONTRACT_STRIDE",
    "CONTRACT_TABLE",
    "LOAN_STATUS",
    "contracts_table_spans",
    "locate_contracts",
    "scrape_unknown_39",
    "scrape_contracts",
    # Currencies
    "CURRENCIES_TABLE",
    "CURRENCY_HEAD",
    "CURRENCY_TAIL",
    "scrape_currencies",
    # Languages
    "LANGUAGES_TABLE",
    "LANGUAGE_HEAD",
    "LANGUAGE_TAIL",
    "languages_table_spans",
    "locate_languages",
    "scrape_languages",
    # Match Slots
    "MATCH_SLOTS_TABLE",
    "MATCH_SLOT",
    "MATCH_SLOT_NO_CLUB",
    "MATCH_SLOT_STRIDE",
    "locate_match_slots",
    "match_slots_table_spans",
    "scrape_match_slots",
    # Matches
    "EVENT_TYPE",
    "MATCHES_TABLE",
    "MatchTableError",
    "check_against_fixtures",
    "locate_matches",
    "matches_table_spans",
    "scrape_matches",
    # Names
    "FIRST_NAMES_TABLE",
    "NAME_ID_ENTRY",
    "NAME_ID_STRIDE",
    "NICKNAMES_TABLE",
    "SURNAMES_TABLE",
    "chain_id_tables",
    "discover_id_tables",
    "locate_first_names",
    "locate_name_tables",
    "locate_nicknames",
    "locate_surnames",
    "walk_browse",
    "walk_browse_bounds",
    # Nations
    "NATION_HEAD",
    "NATION_TAIL",
    "NATIONS_TABLE",
    "locate_nations",
    "nations_table_spans",
    "scrape_nations",
    # Officials
    "OFFICIAL",
    "OFFICIAL_STRIDE",
    "OFFICIALS_TABLE",
    "scrape_officials",
    # Person Info
    "INFO_HEAD",
    "INFO_LAYOUT",
    "NO_CLUB",
    "PERSONALITY",
    "PERSON_FIELDS",
    "PERSON_INFO",
    "PERSON_INFO_TABLE",
    "locate_person_info",
    "person_info_table_spans",
    "scrape_person_info",
    "scrape_players",
    # Player Attributes
    "PLAYER_ATTRIBUTES_TABLE",
    "locate_player_attributes",
    "record_for",
    "scrape_player_attributes",
    # Rounds
    "ROUND_HEAD",
    "ROUND_TRAILER",
    "ROUND_TRAILER_WIDTH",
    "ROUNDS_TABLE",
    "round_names_map",
    "scrape_rounds",
    # Stadiums
    "STADIUM_HEAD",
    "STADIUM_HEADER",
    "STADIUMS_TABLE",
    "locate_stadiums",
    "scrape_stadiums",
    # Staff
    "FORMATION_SLOTS",
    "HIDDEN_OFFSETS",
    "STAFF",
    "STAFF_ATTRS",
    "STAFF_FIELDS",
    "STAFF_FORMATION_SLOTS",
    "STAFF_GRID_STRIDE",
    "STAFF_HIDDEN_OFFSETS",
    "STAFF_STRIDE",
    "STAFF_TABLE",
    "formation_catalog",
    "reputation_tier",
    "scrape_staff_attributes",
    "scrape_staff_roles",
    "style",
]
