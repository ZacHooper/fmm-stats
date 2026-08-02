# FM-Parser Visualiser: Implementation Plan

A bespoke Web UI for reverse-engineering Football Manager Mobile `.fms` save files, featuring a virtualised hex grid, live data inspection, minimap region navigation, fuzzy searching, and save-file diffing.

## 🏗️ Architecture & Tech Stack

### Backend (Python)
*   **Framework:** FastAPI + Uvicorn. Lightweight, fast, and native async.
*   **Core Logic:** Wraps the existing `fmparser.save` mmap logic.
*   **Search Engine:** Python's native `re` module applied to raw byte strings (`b'\x00'`) for blazing fast pattern matching across the 60MB map.
*   **Data Types:** `struct` module for unpacking bytes into floats/ints for the inspector.

### Frontend (Web)
*   **Framework:** React 18 + TypeScript + Vite.
*   **Styling:** Tailwind CSS (perfect for building dense, data-heavy grid UIs quickly).
*   **Virtualisation:** `react-virtuoso` (handles scrolling through 3.75 million rows of hex without crashing the browser).
*   **Visualisations:** HTML5 `<canvas>` for the minimap and `recharts` for the entropy/data plotting.

---

## 🗺️ Implementation Phases

### Phase 1: Core Scaffolding & The Virtualised Grid
**Goal:** Get the save file rendering in the browser without lagging.
1.  **Backend:** Create FastAPI app.
    *   Endpoint: `GET /api/files` (list `.fms` in directory).
    *   Endpoint: `GET /api/chunk/{filename}?offset=N&size=M` (return raw bytes + ASCII).
2.  **Frontend:** Scaffold Vite/React app.
    *   Implement `react-virtuoso` grid. The grid pretends to be 60MB / 16 bytes = 3,750,000 rows long.
    *   As the user scrolls, fetch chunks (e.g., 4KB at a time) from the FastAPI backend and render them.

### Phase 2: The Inspector & Minimap (Context)
**Goal:** Make sense of the data and navigate quickly.
1.  **Inspector Panel:** 
    *   When clicking a hex byte, the UI sends the offset to the backend (or handles it in JS using `ArrayBuffer`).
    *   Display the clicked byte and the following 3-7 bytes parsed as: `int8`, `uint8`, `int16`, `uint16`, `int32`, `uint32`, `float32` (toggle between Little/Big Endian).
2.  **Minimap integration:**
    *   Backend Endpoint: `GET /api/regions` (pulls from `fmparser/regions.py`).
    *   Frontend: Draw a vertical canvas bar. Paint different colours for the `info`, `matches`, and `attributes` regions.
    *   Clicking the canvas updates the virtualised grid offset.

### Phase 3: Fuzzy Search & Diff Engine (The Detective Tools)
**Goal:** Find unknown structures and changes.
1.  **Fuzzy Search:**
    *   Backend parses a custom syntax: `A5 ?? ?? 01` (A5 followed by any two bytes, then 01).
    *   Backend converts this to a regex byte pattern: `b'\xA5..\x01'`, runs it against the `mmap`, and returns an array of offsets.
    *   Frontend paints search results onto the Minimap as bright tick marks.
2.  **Diff Mode:**
    *   UI loads File A (`mid.fms`) and File B (`end.fms`).
    *   Render side-by-side or interleaved grids.
    *   Backend returns a boolean array of changed bytes. Highlight them in red.

### Phase 4: Dynamic Structs & Entropy Plotting
**Goal:** Validate hypotheses visually.
1.  **Struct Builder:**
    *   UI allows you to type a format string (e.g., `H H f B B` for 2x uint16, 1x float, 2x uint8).
    *   The Inspector parses the next $N$ bytes according to this struct and highlights the chunk in the hex view.
2.  **Data Plotting:**
    *   Select a range of bytes. Plot their integer values on a simple line chart.
    *   *Use case:* Identifying arrays of integers (sawtooth pattern) vs compressed data (random static).

---

## 📁 Directory Structure
```text
fm-parser/
├── fmparser/          # Existing logic
├── visualizer/        # NEW Web App Root
│   ├── backend/       # FastAPI app
│   │   ├── main.py    
│   │   └── routes.py
│   └── frontend/      # React App
│       ├── src/
│       │   ├── components/
│       │   │   ├── HexGrid.tsx
│       │   │   ├── Minimap.tsx
│       │   │   └── Inspector.tsx
│       │   └── App.tsx
│       ├── package.json
│       └── vite.config.ts
```