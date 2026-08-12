# Light Results Ring Buffers & Missing Games

**Date:** August 2026

## The Problem
We were noticing that our end-of-season saves were missing the first ~19 games of the simulated non-managed leagues (like Danish 3. Division), despite the managed club retaining all 32-34 of its matches. Furthermore, we suspected our parser was artificially gating fixtures because we were skipping ~90% of the bytes in the `light_results` region.

## The Discovery
Through brute-force byte scanning of the entire `.fms` save file, we discovered two major architectural facts about how Football Manager Mobile handles non-managed ("light") match results:

### 1. The Game Engine literally deletes old fixtures (Rolling Window)
The game does not store the full 32+ game history for non-managed clubs in a single save file. To save memory, it allocates fixed-size ~1.2MB arrays. As the season progresses past ~13-15 games, the engine **physically overwrites the oldest fixtures** with new ones. 
- A mid-season save will have matches 1-15.
- An end-season save will have matches 16-32.
- The raw data for matches 1-15 physically ceases to exist in the end-season file. 

*Conclusion:* The `light_results` ring buffer DOES physically delete old matches. However, the game UI still displays full historical fixture lists. This means the complete season scores are NOT lost—they are simply stored in a completely different data structure (likely the massive fixture/schedule arrays in the 55MB region). We just haven't mapped the schedule array parser yet. By extracting `start`, `mid`, and `end` saves into DuckDB, we use SQL to stitch the overlapping rolling windows back into a complete timeline.

### 2. Multiple Buffers & The Marker Myth
The parser used to gate fixtures by enforcing a strict marker byte `FLAG_HI = (0x40, 0xc0)`. It also only looked for the *single* densest 1.2MB region in the file.
- **Multiple Regions:** We found up to 7 distinct ~1.2MB arrays scattered throughout the 63MB save (likely partitioned by continent or competition type, such as English leagues vs Belgian leagues).
- **The Marker is flexible:** Valid fixtures also use `0x41`, `0x00`, and `0x42xx`. The `0x42xx` marker is particularly tricky because it completely overwrites the Competition CID bytes with a flag (which means we can't easily auto-assign them to a league, but they are valid matches).

*Solution Implemented:* We rewrote `fmparser/lightresults.py` to:
1. Strip out the `FLAG_HI` marker check completely. If the struct is physically sound (valid home TID + valid away TID + score <= 30 + valid year), we parse it.
2. Use `find_light_regions` (plural) to locate *every* active ring buffer across the entire save file, sweep all of them, and then globally deduplicate mirror records.

## What about the Standings Table?
If the game deletes raw matches, how does it display the League Table UI?
We scanned the `6MB-8MB` region of the file and found that FM stores pre-calculated `[Played][W][D][L][Pts]` records. However, these are tightly interleaved with fragmented UI cache pointers (`0x7FFF` null terminators, font/color flags, promotion zone markers) rather than a clean database array. Reverse-engineering this UI memory is extremely fragile and prone to breaking on game updates. While our DuckDB historical `UNION` strategy guarantees 100% accurate match histories without reverse-engineering the UI/Schedule cache, we now know it is mathematically possible to pull the full season from a single end-save if we decode the master fixture schedule block (which stores the scores for every Fixture ID).