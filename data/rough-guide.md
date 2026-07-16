
# Hex Editing in Football Manager Mobile — A Practical Guide

*Compiled from the "Hexer's Workshop: It's all about Hex (FMM21 and beyond)" thread on FMM Vibe (NguyenDucAnh, Rus7M, Scratch, zobirin90, and others). Applies to FMM21 and later.*

---

## Before you touch anything

**Back up your savefile.** Copy it somewhere safe before making a single edit. A wrong byte can corrupt the save and there is no undo.

Ground rules from the workshop:

- Use a **genuine copy of FMM** from the App Store or Google Play.
- Hidden attributes **cannot** be changed with the in-game editor (IGE) — hex is the only route.
- Regen faces reportedly **cannot** be added via hex.

---

## What you need

- **Hex editor** — HxD (Windows), HEX Editor by First Row (Android; has a file-compare feature).
- **ID source** — sortitoutsi.net (the number in a player/club URL is their Unique ID).
- **Converter** — Google `"<number> to hex"`.
- **Optional helper** — the AM21 scouting app makes grabbing search strings and reading CA/PA much faster.

---

## Core concepts (terminology)

| Term | Meaning |
| ------ | --------- |
| **Hex editing** | Editing the save directly in hexadecimal (base 16: `00`–`0F` = 0–15). |
| **Digit** | One value shown as two chars, e.g. `1A`. |
| **Value** | A string of digits, e.g. `AA BB`. |
| **UID** | Unique ID; from the sortitoutsi URL. Used for searching/identification. Manager profiles have none. |
| **TID** | True ID — what matters for edits. 4 digits, `XX XX 00 00`, right before the UID. |
| **SID** | Stats ID — needed for stats/hidden attributes; sits at the end of the info field. |
| **NID** | Nationality ID — home nation; constant across saves; right behind a team's 3-letter code. |
| **Information field** | The block of bytes holding all data for one entity. Length varies. |

### Big vs Little Endian

The game stores numbers in **Little Endian**; Google gives **Big Endian**. Reverse the byte pairs.

- `AA BB CC DD` (Big) → `DD CC BB AA` (Little).
- **Padding:** if the hex has an odd number of chars (or fewer than 3), pad zeros in front to reach at least 4 chars before reversing.
- Example: `1234567` → padded `01 23 45 67` → Little Endian `67 45 23 01`. *(The OP wrote `...32 01`, a typo a reader flagged.)*

---

## Step 1 — Convert a UID and find a player

1. Look up the player on sortitoutsi. Example: Abdelhak Nouri, UID **37045583**.
2. Convert to hex: `235454F`.
3. Pad (7 chars → 8): `02 35 45 4F`.
4. Reverse to Little Endian: **`4F 45 35 02`**.
5. Search that byte string in your hex editor — you land at the start of the player's **information field**.

**Faster UID trick (C21GERMAIN):** put the player in a shortlist or save your team selection, then open the file — the UID appears as the code right after a long string of zeros.

---

## Step 2 — Reading an information field (Nouri example)

- `D5 52 00 00` — **TID** (used for most edits). Then UID `4F 45 35 02`.
- `86 07 00 00` / `7C 04 00 00` — first-name / last-name IDs. `FF FF FF FF` = no nickname.
- `5B 00 CD 07` — **DOB**. Year 1997 → `7CD` → `CD 07`. Day 92 (April 2), minus 1 = 91 → `5B` → `5B 00`.
- `1D 00 9E 00 1D 00 01` — nationality, second nationality, declared national team, then role flag (`01` = player, `10` = manager). `1D 00` = Morocco, `9E 00` = Netherlands.
- `4B 00 E6 07` — last call-up date (rarely matters).
- `12 03` / `00 00` — caps/goals: senior (18 caps, 3 goals) / U21 (first byte = caps, second = goals).
- `25 03` — club TID. `B9 00 E4 07` — last contract date. `69 30` — transfer value.
- `00 CF 3F 00 00` — **SID**.

**Locating IDs quickly:**

- Player/manager/club **TID** = the `XX XX 00 00` immediately before the UID (only `XX XX` used inside the field).
- Stadium **TID** = right behind the stadium name, `00 XX XX` (only `XX XX` matters).
- **NID** = right behind a team's 3-char abbreviation (e.g. `MAR`); constant across saves.

---

## Step 3 — The fast "search mask" technique (Rus7M) — biggest time-saver

Instead of clicking *Find Next* dozens of times, build one wildcard (`?`) search that jumps straight to the block. Use your editor's **hex fragment / wildcard mode**.

- **Player hidden attributes:** `SID + 36 question marks + HexedConsistency`
  - Consistency 12 = `0c` → `SID????????????????????????????????0c`. Last two chars = Consistency.
- **Manager attributes:** `ManagerID2 + 22 question marks + FinancialControl`
  - Rooney: `1a050000??????????????????????06` — finds it instantly.
- **Regen hidden attributes (when ID2 collides):** `ID2 + 28 question marks + Pace`
  - ID2 `bb000000`, Pace 12 = `0c` → `bb000000????????????????????????????0c`. ~99% hit rate.
- **Regen UID (Manv):** `regenUID + 40 question marks + nationCode`
  - Example: `c13d0000` + 40 `?` + `8b00` (England). Cross-reference the nation code from the scrapbooks file.

---

## Step 4 — Editing personality attributes (player)

Search `UID + 78 question marks + HexedAdaptability`. The last two chars = Adaptability, then in order:
**Adaptability, Ambition, Determination, Loyalty, Pressure Handling, Professionalism, Sportsmanship, Temperament.**
The 8 chars just before the long `ff ff` run = the **SID** you need for hidden attributes.

*(These need only the player's ID and can't be edited via IGE.)*

---

## Step 5 — Editing hidden attributes (player)

Search `SID + 36 question marks + HexedConsistency`. Then in order:
**Consistency, Aggression (also IGE-editable), Big Matches, Injury Proneness (lower is better)**, skip 2 chars, **Versatility, Free Kicks, Penalties**, skip 8 chars, **Flair.**

Landmark method (alternative): search ID2 until you hit a region full of `01 01 01 14 01 01 14…` — that's the positions block; hidden skills sit just above it, CA/PA just after.

**Scale:** attributes run **1–20**, where `14` = 20 (max).

---

## Step 6 — The full player record structure (Scratch)

The complete byte map of a player's attribute record (Billy Gilmour example). **Some values are 0–20, some are 0–255** — experiment. Layout differs slightly between saves.

```
34 27 00 00  AE CF 01 00  DF F6 F6 DF EB 06 06 1C 08 0C 0B 07 0C 10 0B 0F 0F 0C 0C 04 0D 0F 26 F5 F4 0D 08 9C A3 0C 9C 9C 9C 9C  01 01 01 01 01 0E 0A 14 0C 0C 0F 0E 01 01 01  0C 14  7E 00  A8 00  9C 18 9C 18 7C 15  00 06 98 00 00  AA 00  41 00
```

1. **ID / codes:** `34 27 00 00` = save-specific code (from the main record, just before the long `FF FF`). `AE CF 01 00` = a second code, normally ignore (add 1, e.g. `AF CF 01 00`, to find the history section).
2. **Attributes** (in order): Crossing, Dribbling, Tackling, Shooting (Finishing), Shooting (Long Shots), Aerial (Heading), Aerial (Jumping), Passing, Decisions, Teamwork (Unselfishness), Pace, Strength, Stamina, Technique, Consistency, Aggression, Big Matches, Injury Proneness, Leadership, Versatility, Set Pieces, Penalties, Creativity, Movement, Positioning, Teamwork (Work Rate), Flair, Handling, Kicking, Agility, Aerial GK, Reflexes, Communication (displayed value modified by Leadership), Throwing.
3. **Positions** (0–20): `01 01 01 01 01 0E 0A 14 0C 0C 0F 0E 01 01 01` → GK, Sweeper (unused), DL, DC, DR, DMC, ML, MC, MR, AML, AMC, AMR, ST, DML, DMR.
4. **Feet** (0–20): left, then right (`0C`, `14`). Sits immediately before CA/PA.
5. **CA / PA** (both 0–200): CA (`7E 00`) then PA (`A8 00`). *This is how you edit potential.*
6. **Reputations:** home (`9C 18`), current (`9C 18`), world (`7C 15`).
7. **Other:** `00 06 98 00 00` — first `00` = retired from international team (set `01`); the rest relates to body shape.
8. **Height & Weight:** height (`AA 00`), weight (`41 00`) — stored but not shown in-game.

---

## Editing managers / staff attributes (Rus7M, Rooney example)

1. Find the manager by ID (Rooney UID = `a6 f2 4d 00`). Just before a run of `ff ff ff...` sits his **ID2** (save-specific; here `1a 05 00 00`).
2. Search ID2 (or use the mask above). Landmark: **Financial Control** is the first attribute — when its value (e.g. `06`) sits below 12 values, you're in the right place.
3. Layout from that anchor:
   - After ID2: **CA** (`73` = 115), **PA** (`96` = 150), then reputation.
   - Line 12: Financial Control
   - Lines 13–14: Outfield / Goalkeeping coaching
   - Line 16: Discipline
   - Lines 18–20: Judging Ability / Judging Potential / Man Management
   - Line 22: Motivating
   - Line 26: Tactical Knowledge
   - Line 27: Youth
   - Line 28: favourite formation (`0a` = 4-3-3)

---

## Regens

- Personality/hidden attributes edit exactly like normal players — only **searching** is harder (ID2 collides). Use the Pace search mask.
- **UID** is found via personal info (DOB, nation) and the mask above.
- **Faces** still can't be added via hex (unresolved).

---

## Beyond players: clubs, competitions, files

- **Club affiliates** — addable/changeable via hex (remember to change the affiliate's ID).
- **Languages & squad status** — editable (zobirin90 found hidden statuses "Not Needed"/"Not Yet Sure"), full method never posted.
- **League/nation swaps** — done in `club.dat`, swapping the hex for a club's league, cross-referenced with `competition.dat`.
- **Competition rules (advanced, MrCaseiro):** the save contains a decoded copy of `comps.dbc` — search `maintDdE` (each hit marks the end of a competition's rules). Edits apply next season. To edit the source `comps.dbc` in the OBB: strip the first 8 bytes so it starts `02 01 f m f .`, open with a resource archiver, edit, then **repack the OBB with "compress archive" unticked** (otherwise text breaks and saves won't create).

---

## CA/PA the easy way

For editing CA/PA (e.g. an in-game son), **changes.txt is easier than hex** — and it works on both new *and* existing saves (per NguyenDucAnh).

---

## Cheat-sheet

- **Always back up first.**
- Google = Big Endian; game = Little Endian → reverse byte pairs. Pad to ≥4 chars first.
- UID = search/identify. TID = `XX XX 00 00` before the UID = what you edit with. SID = end of field. NID = behind the 3-letter nation code.
- Role flag: `01` player, `10` manager. Attribute scale 1–20, `14` = max (but some record values are 0–255).
- Search masks beat *Find Next*: personality = `UID + 78? + attr`; hidden = `SID + 36? + attr`; manager = `ID2 + 22? + FinControl`; regen = `ID2 + 28? + Pace`.
- Player record order: IDs → attributes → positions → feet → **CA/PA** → reputations → shape → height/weight.

*Source: Hexer's Workshop: It's all about Hex (FMM21 and beyond), FMM Vibe forums.*
