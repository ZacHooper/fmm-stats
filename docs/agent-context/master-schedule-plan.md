# Master Schedule Array: Parsing Plan

**Date:** August 2026

## The Breakthrough
While the `light_results` array is a 1.2MB rolling ring buffer that drops old matches, the game's UI retains full historical fixtures for all leagues. The full season history lives in a massive relational memory block spanning roughly **55MB to 58.5MB**.

## The Data Structure (Relational/Pointer-Based)
Unlike the flat `[Home][Away][ScoreH][ScoreA]` structure of the light results, the Master Schedule uses a 3-hop pointer system:

1. **Schedule Array (55MB - 58MB Region):**
   Stores fixtures mapped to competitions.
   Contains the sequence: `[Home Team ID (2 bytes)] [Away Team ID (2 bytes)] [Competition CID (2 bytes)] [Fixture Pointer (4 bytes)]`
   
2. **Match Played Events (55MB Region):**
   Appended later in the file as matches are actually played.
   Format: `[Status Byte (00/01)] [Home ID] [Away ID] [Fixture Pointer]`... 
   *(Note: The score bytes are not immediately apparent here).*

3. **Data Dictionary Hop (~34MB Region):**
   The 4-byte Fixture Pointer (e.g., `d3 00 02 08`) points back to a massive dictionary block around 34MB (`0x2000000`). 
   *Current investigation:* Identifying the exact location of the `1-0` and `1-1` scores relative to this pointer. 

## The Attack Plan

### Phase 1: Ground Truth Anchoring (COMPLETED)
- Checked `denmark-end-22.fms`: Found exactly 22 unique match-ups for Frem in the 55MB block (the complete regular season schedule).
- Validated pointers and Match Played Event structs. 

### Phase 2: Diffing the State (COMPLETED)
- Checked `denmark-start.fms`: The pre-allocated match pointers are present, but the "Match Played" appended events are absent.
- Checked `denmark-mid-22.fms`: Only the first half of the Match Played events exist. The array physically grows as matches complete.

### Phase 3: The Data Dictionary Hop (IN PROGRESS)
- Traced the `d3 00 02 08` pointer (Frem vs Dalum) to `Offset 0x20d6c67`.
- Checking surrounding bytes for actual match scores (Frem 1-0 Dalum, Dalum 1-1 Frem). We found `02 01` trailing the pointer, but need to verify if this is a score or a date/event enum since the actual score was 1-0.

### Phase 4: Build the Relational Join (PENDING)
Once we confirm the exact score offset relative to the Fixture Pointer, we will write `extract_master_schedule.py` to extract the full 32-game season.
