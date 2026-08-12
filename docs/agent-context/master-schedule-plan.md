# Master Schedule Array: Parsing Plan

**Date:** August 2026

## The Breakthrough
While the `light_results` array is a 1.2MB rolling ring buffer that drops old matches, the game's UI retains full historical fixtures for all leagues. We proved this data exists in the save file by searching for specific Round 1 match-ups (e.g., FC Roskilde vs VSK Aarhus) in an end-of-season save. 

The full season history lives in a massive relational memory block spanning roughly **55MB to 58.5MB**.

## The Data Structure (Relational/Pointer-Based)
Unlike the flat `[Home][Away][ScoreH][ScoreA]` structure of the light results, the Master Schedule is highly fragmented and relational:
1. **Fixture Pairings (~55.7MB):** We found arrays linking Team IDs together, but the scores weren't immediately adjacent in the expected format.
2. **Competition Mapping (~58.4MB):** We found arrays linking Team IDs directly to Competition CIDs (e.g., VSK Aarhus `ca 14` -> Danish 3. Div `7b 04`).
3. **The Pointers:** The scores are likely stored in standalone event structs linked by Fixture IDs or memory offsets.

*Hypothesis (Zac):* The engine likely uses a multi-hop pointer system similar to how player names are resolved. A Team/Competition record points to a Fixture ID in the data dictionary, which then points to the actual match result struct containing the scores.

## The Attack Plan
To reverse-engineer the Master Schedule without guessing, we will execute the following phases:

### Phase 1: Ground Truth Anchoring
Use the exact Round 1 matches from the user's screenshot (e.g., Frem vs Dalum 1-0, FC Roskilde vs VSK Aarhus 1-2). We will scan the entire 55MB-58MB region for the literal score bytes (`01` and `00`, `01` and `02`) appearing within 16-32 bytes of the Team IDs. If they aren't there, we know the scores are stored in a separate table.

### Phase 2: Diffing the State (Unplayed vs Played)
We have a `start`, `mid`, and `end` save for the exact same career.
- We will locate a specific match-up (e.g., Round 30) in the `start` save. It will be scheduled, but unplayed.
- We will diff that exact memory location against the `end` save. 
- The bytes that change will isolate the "Score/Played Status" pointers.

### Phase 3: The Data Dictionary Hop
If the bytes surrounding the Team IDs in the 55MB region are large integers (e.g., `u32` indices), we will run them through the existing `data_dict` parser (`dump_datadict.py`). We will test Zac's theory: checking if these integers are dictionary keys that resolve to the score structs.

### Phase 4: Build the Relational Join
Once we map the jumps (e.g., `Competition -> Schedule Array -> Fixture ID -> Score Struct`), we will write a new extractor script (`extract_schedule.py`) that joins these tables in memory and spits out the full 32-game season.
