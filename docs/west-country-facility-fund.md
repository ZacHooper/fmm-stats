# West Country Facility Development Fund — The South West Football Accord

A house-rule framework for the Truro City career (`career-notes/truro.md`): as Truro climbs the pyramid and unlocks new counties, the clubs and County FAs of the South West sign on to a regional infrastructure pact — pooling **5% FIFA Solidarity on local academy graduates** and a **1% regional turnover levy on all other club sales** (with **70% ring-fenced for the generating club/county** and **30% shared across the region**) to upgrade Training (`academy`) and Youth (`facilities`) ratings.

---

## 1. The Rules of the Accord

1. **Phased County Entry ("Prove It Works First"):**
   * A county's clubs only pay into (and draw from) the Accord once Truro reaches the division that unlocks that phase (`[careers.truro.eligible_origin_clubs]` in `fmm.toml`):
     * **Phase 1 (Start — National League South / National League):** Cornwall & Devon (14 clubs).
     * **Phase 2 (League Two):** + Somerset & Dorset (15 clubs, including AFC Bournemouth & Yeovil Town).
     * **Phase 3 (Championship):** + Bristol, Gloucestershire & Wiltshire (25 clubs, including Bristol City, Bristol Rovers, Swindon Town, Cheltenham Town & Forest Green Rovers).
2. **The Two-Tier Levy (Capped at 5% per Transfer):**
   * **5% Academy Graduate Solidarity (`origin_club_tid` in an unlocked county):** Whenever a player who came through an unlocked county's youth academy is transferred for a fee *anywhere in the world* (`site.transfers` where `in_career AND fee_gbp > 0`), the real-world **5% FIFA Solidarity** deduction goes into the Fund.
   * **1% Regional Club Turnover Levy (`from_club_tid` in an unlocked county, non-graduate):** Whenever an unlocked South West club sells a non-local player for a fee, **1% of the sale** goes into the Fund.
   * **The Cap:** If an unlocked club sells one of its *own* academy graduates (both conditions true, e.g. Exeter City selling Sonny Cox), the levy is **capped at 5%** (never 5% + 1% = 6%).
   * **Full Window Scope:** Every `in_career` transfer from the opening summer window (`2026/27` onwards) counts.
3. **The 70% / 30% Selfish Ring-Fence:**
   * **70% Club / County Ring-Fence:** 70% of every pound generated is ring-fenced for the **origin academy club** (on a 5% graduate deal) or the **selling club** (on a 1% turnover deal). It must be spent upgrading that club's facilities first — or, if that club is already maxed out (e.g. AFC Bournemouth at `20 / 20`) or chooses to pass it down, on smaller feeder clubs within the **same county**.
   * **30% Shared Regional Spillover Pot:** 30% of every pound generated flows into the central **West Country Spillover Pot**, which can be spent on **any** club in an unlocked county (including Truro City) or combined with a club's 70% ring-fenced balance to complete a tier jump.
4. **What an Upgrade Buys & Regen Spawn Gate:**
   * Each step buys **+0.5★ (+2 points on the 1–20 scale)** on **one track** (either **Training Facilities** `academy` or **Youth Facilities** `facilities`).
   * **The AI Regen Spawn Gate (from the 10-year Frem dataset):** In FMM, AI clubs only spawn regens if they are in **Tier 1–6 (National League North/South or higher)** and hold **`reputation >= 1,850–1,950`**. `facilities` (`1–20`) determines **how good** a club's regens are once they spawn. Prioritise upgrading clubs already in Tier 1–6 (Truro, Exeter, Plymouth, Torquay) unless also promoting a feeder club into the playable tiers.

---

## 2. The Upgrade Pricing Ladder (`0.5★` to `5.0★`)

In FMM, both Training (`academy` byte) and Youth (`facilities` byte) run from `1` to `20`, where `stars = floor(value / 2) / 2`. Real-world grassroots upgrades are co-funded by the Football Foundation and local councils (65%–75% at non-league level, tapering to 0% at the top end); the **Levy Cost** below is the net cash required from the Fund.

| Step | Rating Jump | Star Jump | In-Game Label | Levy Cost (1 Track: Train OR Youth) | Cumulative (1 Track from 0.5★) | Levy Cost (Both Tracks) | Cumulative (Both Tracks from 0.5★) | Real-World Standard & Co-Funding Assumption |
|---|---|---|---|---|---|---|---|---|
| **1** | `1–2` → `3–4` | `0.5★` → `1.0★` | Poor → Basic | **£250k** | **£250k** | **£500k** | **£500k** | Floodlit 3G pitch + clubhouse (~£1.0M gross; 75% Football Foundation / Council grant) |
| **2** | `3–4` → `5–6` | `1.0★` → `1.5★` | Basic → Below Average | **£500k** | **£750k** | **£1.00M** | **£1.50M** | Pitch drainage, S&C gym & physio cabins (~£1.5M gross; 65% grant co-funding) |
| **3** | `5–6` → `7–8` | `1.5★` → `2.0★` | Below Average → Adequate | **£1.00M** | **£1.75M** | **£2.00M** | **£3.50M** | EFL League Two entry base (Torquay / Cheltenham tier; 50% county co-funding) |
| **4** | `7–8` → `9–10` | `2.0★` → `2.5★` | Adequate → Average | **£1.50M** | **£3.25M** | **£3.00M** | **£6.50M** | EFL League One modular pavilion (**Exeter City Cliff Hill** standard) |
| **5** | `9–10` → `11–12` | `2.5★` → `3.0★` | Average → Good | **£3.00M** | **£6.25M** | **£6.00M** | **£12.50M** | EPPP Cat 3 / dedicated academy hub (**Plymouth Argyle Foulston Park** club share) |
| **6** | `11–12` → `13–14` | `3.0★` → `3.5★` | Good → Great | **£4.00M** | **£10.25M** | **£8.00M** | **£20.50M** | EPPP Cat 2 / Championship multi-pitch complex |
| **7** | `13–14` → `15–16` | `3.5★` → `4.0★` | Great → Excellent | **£5.00M** | **£15.25M** | **£10.00M** | **£30.50M** | EPPP Cat 1 / High Performance Centre (**Bristol City Robins HPC** standard) |
| **8** | `15–16` → `17–18` | `4.0★` → `4.5★` | Excellent → Superb | **£6.00M** | **£21.25M** | **£12.00M** | **£42.50M** | Full-size indoor dome, hydrotherapy & sports science wing |
| **9** | `17–18` → `19–20` | `4.5★` → `5.0★` | Superb → State of the Art | **£8.00M** | **£29.25M** | **£16.00M** | **£58.50M** | Premier League elite campus (**AFC Bournemouth Canford Magna** standard) |

### Key Cumulative Totals (Single Club from Scratch `0.5★` → Target)
* **Grassroots (`0.5★`) to EFL Standard (`2.0★`):** **£1.75M** per track (**£3.50M** for both Training & Youth).
* **Grassroots (`0.5★`) to EPPP Cat 3 (`3.0★`):** **£6.25M** per track (**£12.50M** for both).
* **Grassroots (`0.5★`) to Championship / Cat 1 (`4.0★`):** **£15.25M** per track (**£30.50M** for both).
* **Grassroots (`0.5★`) all the way to State of the Art (`5.0★`):** **£29.25M** per track (**£58.50M** for both).

---

## 3. Season 1 Ledger (`2026/27` Full Window — Phase 1: Cornwall & Devon)

Extracted from `fm-truro.duckdb` (`truro-2027-07-02`, `site.transfers WHERE in_career AND fee_gbp > 0`) for all 14 Phase 1 Cornwall & Devon clubs:

### A. All 19 Qualifying Transfers in 2026/27

| Window | Player | Origin Academy | Selling Club | Buying Club | Fee (£) | Rule & Rate | Total Levy (£) | 70% Club Ring-Fence (£) | 30% Regional Spillover (£) | Ring-Fence Beneficiary |
|---|---|---|---|---|---|---|---|---|---|---|
| Summer 26 | **Ollie Watkins** | **Exeter City** | Aston Villa | Al Hilal | £50,000,000 | 5% Graduate | **£2,500,000** | £1,750,000 | £750,000 | **Exeter City** |
| Summer 26 | **Lorent Tolaj** | FC Sion | **Plymouth Argyle** | Bristol City | £4,000,000 | 1% Club Sale | **£40,000** | £28,000 | £12,000 | **Plymouth Argyle** |
| Summer 26 | **Jayden Wareham** | Woking | **Exeter City** | Wycombe Wanderers | £1,700,000 | 1% Club Sale | **£17,000** | £11,900 | £5,100 | **Exeter City** |
| Summer 27 | **Sonny Cox** | **Exeter City** | **Exeter City** | Swindon Town | £130,000 | 5% Grad (Cap) | **£6,500** | £4,550 | £1,950 | **Exeter City** |
| Summer 26 | **Jamie Reid** | **Exeter City** | Stevenage | Reading | £100,000 | 5% Graduate | **£5,000** | £3,500 | £1,500 | **Exeter City** |
| Winter 27 | **Reece Cole** | Brentford | **Exeter City** | Bradford City | £341,000 | 1% Club Sale | **£3,410** | £2,387 | £1,023 | **Exeter City** |
| Summer 26 | **Jack Fitzwater** | West Brom | **Exeter City** | Notts County | £274,000 | 1% Club Sale | **£2,740** | £1,918 | £822 | **Exeter City** |
| Summer 26 | **Alfie Pond** | **Exeter City** | Wolves | Chesterfield | £50,000 | 5% Graduate | **£2,500** | £1,750 | £750 | **Exeter City** |
| Winter 27 | **Levi Ives** | **Torquay United** | Coleraine | Cheltenham Town | £32,000 | 5% Graduate | **£1,600** | £1,120 | £480 | **Torquay United** |
| Summer 26 | **Brendan Wiredu** | Charlton Athletic | **Plymouth Argyle** | Salford City | £150,000 | 1% Club Sale | **£1,500** | £1,050 | £450 | **Plymouth Argyle** |
| Summer 27 | **Seb Campbell** | **Plymouth Argyle** | **Plymouth Argyle** | Tamworth | £17,000 | 5% Grad (Cap) | **£850** | £595 | £255 | **Plymouth Argyle** |
| Summer 27 | **Matt Worthington** | AFC Bournemouth | **Torquay United** | Worthing | £72,000 | 1% Club Sale | **£720** | £504 | £216 | **Torquay United** |
| Summer 26 | **Sam Dreyer** | Stevenage | **Torquay United** | Harrogate Town | £70,000 | 1% Club Sale | **£700** | £490 | £210 | **Torquay United** |
| Summer 26 | **Dylan Morgan** | Forest Green | **Torquay United** | Crawley Town | £65,000 | 1% Club Sale | **£650** | £455 | £195 | **Torquay United** |
| Summer 26 | **Johnly Yfeko** | Tottenham | **Exeter City** | Kilmarnock | £50,000 | 1% Club Sale | **£500** | £350 | £150 | **Exeter City** |
| Summer 26 | **Thomas McHale** | **Truro City** | Elgin City | Nairn County | £7,000 | 5% Graduate | **£350** | £245 | £105 | **Truro City** |
| Summer 26 | **Jordan Young** | Swindon Town | **Torquay United** | Worthing | £20,000 | 1% Club Sale | **£200** | £140 | £60 | **Torquay United** |
| Summer 26 | **Will Jenkins-Davies** | **Plymouth Argyle** | Bath City | Weston-super-Mare | £2,000 | 5% Graduate | **£100** | £70 | £30 | **Plymouth Argyle** |
| Summer 26 | **Dominic Johnson-Fisher** | Steyning Town | **Truro City** | Worthing | £1,000 | 1% Club Sale | **£10** | £7 | £3 | **Truro City** |
| **Total** | **19 Deals** | | | | **£57,081,000** | | **£2,584,330** | **£1,809,031** | **£775,299** | |

### B. End-of-Season 1 (`2026/27`) Fund Balances & Available Upgrades

| Pot / Beneficiary | Deals | Gross Transfer Fees | Total Levy Generated | 70% Ring-Fenced Balance | 30% Contributed to Spillover | 1% Seller Tax to Deduct from Club Budget | Current Transfer Budget (`2 Jul 2027`) | What It Can Buy Right Now (`Jul 2027`) |
|---|---|---|---|---|---|---|---|---|
| **Exeter City (Ring-Fenced 70%)** | 8 | £52,645,000 | £2,537,650 | **£1,776,355** | £761,295 | **-£23,650** *(on £2.365M non-grad sales)* | £362,051 | **Step 4 Youth Upgrade (`2.0★ → 2.5★`, `9 → 11` for £1.50M)**, leaving **£276,355** in Exeter's pot! |
| **Plymouth Argyle (Ring-Fenced 70%)** | 4 | £4,169,000 | £42,450 | **£29,715** | £12,735 | **-£41,500** *(on £4.15M non-grad sales)* | £2,536,542 | Saving toward Step 4 (`2.0★ → 2.5★`, £1.50M) |
| **Torquay United (Ring-Fenced 70%)** | 5 | £259,000 | £3,870 | **£2,709** | £1,161 | **-£2,270** *(waived/deferred: budget at £0)* | £0 *(-£3,050)* | Saving toward Step 4 (`2.0★ → 2.5★`, £1.50M) |
| **Truro City (Ring-Fenced 70%)** | 2 | £8,000 | £360 | **£252** | £108 | **-£10** *(on £1k non-grad sale)* | £79,633 | Combine with Regional Spillover Pot below |
| **Shared West Country Spillover Pot (30%)** | 19 | — | — | **£775,299** | — | — | — | **Truro City Step 1 Youth (`0.5★ → 1.0★`, `3 → 5` for £250k) + Step 2 Training (`1.0★ → 1.5★`, `4 → 6` for £500k) = £750k**, leaving **£25,551** (incl. Truro's £252)! |

---

## 4. Bookkeeping & Accounting Workflow (End-of-Season Reconciliation)

Because `fm-truro.duckdb` automatically captures every transfer in the world via `site.transfers` (`mart.fact_transfer`) and every club's live transfer budget via `club_rows`, keeping the books takes **zero manual spreadsheet work during the season**. Just run an **Annual July Rollover Audit** once a year (right around `1–2 July`):

1. **The 5% FIFA Graduate Solidarity (Thin Air / External FIFA Pool — No Budget Deduction):**
   * In real life, the 5% FIFA Solidarity Mechanism is withheld by the **buying club** from the transfer fee before the selling club ever receives the wire (e.g. Al Hilal pays Aston Villa 95% and sends 5% to the training clubs; or when Exeter sells its own graduate Sonny Cox to Swindon, Swindon's 5% solidarity stays inside the Accord).
   * You **never** need to subtract the 5% Graduate Solidarity from any South West club's in-game budget — it comes out of thin air from the buying club's gross fee.
2. **The 1% Regional Club Turnover Levy (Deducted Only on Non-Graduate Sales by Unlocked SW Clubs):**
   * The only cash a South West club actually owes out of its own pocket is the **1% Regional Turnover Tax** on **non-graduate sales** (`is_p1_seller AND NOT is_p1_grad`).
   * At the annual July rollover, check the club's **1% Seller Tax Owed** against its current `transfer_budget` in the In-Game Editor (or `club_rows`):
     * **Threshold Rule:** Only bother opening the editor to subtract it if a club owes **>= £10,000** (or let smaller amounts roll over until they cross £10k).
     * **Insolvency / Overdraft Guard:** If an AI club's transfer budget is `£0` or negative (in `club_rows`, a negative signed 32-bit int wraps to `~4,294,964,246`, like Torquay United at `-£3,050` on `truro-2027-07-02`), either **defer** the deduction until they have a positive budget or let their 70% ring-fenced credit absorb it.
   * **For Season 1 (`2026/27`):**
     * **Plymouth Argyle:** Subtract **£41,500** from their `£2,536,542` transfer budget → new budget **`£2,495,042`**.
     * **Exeter City:** Subtract **£23,650** from their `£362,051` transfer budget → new budget **`£338,401`**.
     * **Torquay United (`£2,270`) & Truro City (`£10`):** Under £10k (and Torquay's budget is £0), so waive/defer.
3. **Applying the Facility Upgrades & Recording the Spend:**
   * When a club's **70% Ring-Fenced Balance** (or an allocation from the **30% Shared Spillover Pot**) covers a step on the Pricing Ladder (Section 2):
     * Bump the club's **Training (`academy`)** or **Youth (`facilities`)** rating by **`+2` (`+0.5★`)** in the editor.
     * Log a one-line entry in the **Spent Upgrades Ledger** below. Our DuckDB audit query simply sums all `in_career` levy receipts to date and subtracts the rows in the Spent Upgrades Ledger to give you the live balances every season!

### C. Spent Upgrades Ledger (Running Log)

Record each facility upgrade here as you apply it in-game so future DuckDB queries can compute `net_balance = cumulative_levy_earned - cumulative_spent`:

| Date Applied | Beneficiary Club | TID | Facility Track | Old Rating | New Rating | Cost (£) | Funded From | Notes |
|---|---|---|---|---|---|---|---|---|
| *Pending (`2027-07-02`)* | **Exeter City** | `329` | Youth (`facilities`) | `8–9 (2.0★)` | `11 (2.5★)` | £1,500,000 | Exeter 70% Ring-Fence (`£1,776,355`) | Ollie Watkins Al Hilal windfall; leaves £276,355 |
| *Pending (`2027-07-02`)* | **Truro City** | `3125` | Youth (`facilities`) | `3 (0.5★)` | `5 (1.0★)` | £250,000 | 30% Regional Spillover (`£775,299`) + Truro 70% (`£252`) | Step 1 Youth upgrade at Langarth |
| *Pending (`2027-07-02`)* | **Truro City** | `3125` | Training (`academy`) | `4 (1.0★)` | `6 (1.5★)` | £500,000 | 30% Regional Spillover (`£775,299`) | Step 2 Training upgrade at Langarth; leaves £25,551 |

---

## 4. Starting Baseline & Cumulative Cost for Phase 1 Clubs (Cornwall & Devon)

Where the 14 Phase 1 clubs start in `fm-truro.duckdb` (before applying the July 2027 upgrades above), and what it costs the Fund to lift **both** their Training and Youth facilities to key milestones:

| Club | TID | County | Starting (`Train / Youth`) | Starting Stars | Active Tier 1–6? | Cost to Reach `2.0★` | Cost to Reach `3.0★` | Cost to Reach `4.0★` | Cost to Reach `5.0★` |
|---|---|---|---|---|---|---|---|---|---|
| **Plymouth Argyle** | `368` | Devon | `9 / 9` | `2.0★ / 2.0★` | Yes (L1) | £0.00M | £9.00M | £27.00M | £55.00M |
| **Exeter City** | `329` | Devon | `10 / 9` | `2.5★ / 2.0★` | Yes (L1) | £0.00M | £7.50M | £25.50M | £53.50M |
| **Torquay United** | `395` | Devon | `9 / 8` | `2.0★ / 2.0★` | Yes (NLS) | £0.00M | £9.00M | £27.00M | £55.00M |
| **Truro City** | `3125` | Cornwall | `4 / 3` | `1.0★ / 0.5★` | Yes (NLS/NL) | £3.25M | £12.25M | £30.25M | £58.25M |
| **Helston Athletic** | `5335` | Cornwall | `2 / 2` | `0.5★ / 0.5★` | No (`rep 1150`) | £3.50M | £12.50M | £30.50M | £58.50M |
| **Saltash United** | `2392` | Cornwall | `2 / 2` | `0.5★ / 0.5★` | No (`rep 750`) | £3.50M | £12.50M | £30.50M | £58.50M |
| **Torpoint Athletic** | `5332` | Cornwall | `2 / 2` | `0.5★ / 0.5★` | No (`rep 750`) | £3.50M | £12.50M | £30.50M | £58.50M |
| **Plymouth Parkway** | `5326` | Devon | `1 / 1` | `0.0★ / 0.0★` | No (`rep 1250`) | £3.50M | £12.50M | £30.50M | £58.50M |
| **Tiverton Town** | `2370` | Devon | `2 / 1` | `0.5★ / 0.0★` | No (`rep 1850`) | £3.50M | £12.50M | £30.50M | £58.50M |
| **Barnstaple Town** | `2381` | Devon | `2 / 2` | `0.5★ / 0.5★` | No (`rep 1350`) | £3.50M | £12.50M | £30.50M | £58.50M |
| **Bideford** | `2382` | Devon | `1 / 1` | `0.0★ / 0.0★` | No (`rep 1400`) | £3.50M | £12.50M | £30.50M | £58.50M |
| **Buckland Athletic** | `5331` | Devon | `2 / 2` | `0.5★ / 0.5★` | No (`rep 1050`) | £3.50M | £12.50M | £30.50M | £58.50M |
| **Tavistock** | `5258` | Devon | `1 / 1` | `0.0★ / 0.0★` | No (`rep 900`) | £3.50M | £12.50M | £30.50M | £58.50M |
| **Elburton Villa** | `3759` | Devon | `1 / 1` | `0.0★ / 0.0★` | No (`rep 300`) | £3.50M | £12.50M | £30.50M | £58.50M |
| **Phase 1 Total (14 Clubs)** | | | | | | **£38.25M** | **£162.75M** | **£414.75M** | **£806.75M** |

---

## 5. 10-Year Projection (Benchmarked Against the 10-Year Frem Save)

What the **1% Club Sales + 5% Graduate Solidarity (Capped)** model would have generated across the 10 seasons (`2021–2030`) of `fm-frem.duckdb`:

* **Phase 1 (Cornwall & Devon):**
  * AI Club Sales (`£36.13M` at 1%) = **£0.36M**
  * Cornwall & Devon Academy Graduates Sold Worldwide (`£133.99M` at 5%) = **£6.70M**
  * Managed Club Outgoing Sales (`£112.00M` at 5%) = **£5.60M**
  * **10-Year Phase 1 Pot:** **£12.66M**
* **Phase 2 (Somerset & Dorset, once unlocked at League Two):**
  * Club Sales (`£581.60M` at 1%, led by AFC Bournemouth) = **£5.82M**
  * Somerset & Dorset Academy Graduates Sold Worldwide (`£139.96M` at 5%) = **£7.00M**
  * **10-Year Phase 2 Pot:** **£12.82M** *(and because Bournemouth is already `20 / 20`, their 70% Dorset ring-fence cascades directly to Weymouth, Dorchester, Poole, Wimborne & Yeovil!)*
* **Phase 3 (Bristol, Gloucestershire & Wiltshire, once unlocked at Championship):**
  * Club Sales (`£529.04M` at 1%, led by Bristol City & Swindon) = **£5.29M**
  * Phase 3 Academy Graduates Sold Worldwide (`£377.54M` at 5%) = **£18.88M**
  * **10-Year Phase 3 Pot:** **£24.17M**

---

## 6. Real-World Regulatory & South West Construction References

### A. Football Transfer Levies
1. **FIFA Solidarity Mechanism (5%):** Under Article 21 and Annex 5 of the *FIFA Regulations on the Status and Transfer of Players*, **5% of any transfer fee** (excluding training compensation) is deducted and distributed to the club(s) that trained and educated the player between the ages of **12 and 23** (0.25% per season for ages 12–15; 0.50% per season for ages 16–23).
2. **Premier League / EFL Transfer Levy (4%):** English professional clubs pay a mandatory **4% levy** on transfer fees toward the Football Foundation, the EFL Youth Development Grant fund, and the Professional Footballers' Pension Scheme.

### B. South West Training Ground & Academy Construction Receipts (2021–2026)
1. **Grassroots 3G Pitches (`0.5★` → `1.0★`, ~£1.0M–£1.5M gross / £250k club share):**
   * **Football Pyramid Partnership / Football Foundation (2025/26):** A standalone full-size FIFA-quality floodlit 3G pitch costs **£850k–£1.8M** (£1.5M–£3.0M with changing rooms and groundworks). The Football Foundation provides **65%–70% grant funding**, leaving the club and local council to cover the remaining ~£250k–£300k.
   * *Sources:* [Football Pyramid Partnership — 3G Pitches Grant Funding vs Self-Funding](https://footballpyramidpartnership.com/insights-3g-pitches-grant-funding-vs-self-funding.html) · [UK Parliament Written Evidence — Football Foundation](https://committees.parliament.uk/writtenevidence/133834/html)
2. **Truro City — Langarth Sports Hub (`1.0★` Training / `0.5★` Youth, £4.46M stadium + £2.54M community pitch):**
   * **Truro City FC (2024/25):** The main Langarth stadium pitch and facilities cost **£4.46M** (£2.03M from Truro City via the Treyew Road sale + £2.43M Cornwall Council Langarth capital), while the adjacent community pitch and car park cost **£2.54M** (£800k Football Foundation grant + £1.74M Langarth capital).
   * *Sources:* [BBC News — Truro City FC to return home as sports hub approved](https://www.bbc.co.uk/news/articles/cv2080emm7eo) · [ITV West Country](https://www.itv.com/news/westcountry/2024-02-15/cornish-football-club-to-return-to-home-city-next-season)
3. **Exeter City — Cliff Hill Training Ground Redevelopment (`2.5★` Training `10` / `2.0★` Youth `9`, £2.98M):**
   * **Exeter City FC (2022):** Constructed a new two-storey modular building at Cliff Hill (expanded gym, dedicated canteen, larger changing and physiotherapy rooms, match analysis theatre) for First Team and Academy use. Originally budgeted at £2.2M and completed at **£2,978,000** following post-pandemic construction inflation, funded via player transfer windfalls and a £600k Supporters' Trust loan.
   * *Sources:* [Exeter City FC — Work begins on £2.9m training facility](https://exetercityfc.co.uk/news/2022/may/turf-cutting) · [BBC Sport — Cliff Hill training ground costs](https://www.bbc.co.uk/sport/football/61492783)
4. **Plymouth Argyle — Foulston Park / Brickfields Academy (`2.0★` → `3.0★+` Academy Redevelopment, £21M–£23M total / £11M–£12M club share):**
   * **Plymouth Argyle FC (2023–2026):** Permanent academy complex at Brickfields (Devonport) featuring three grass pitches, an all-weather 3G pitch, indoor training barn, classrooms, changing rooms, and sports science facilities. Total project cost is **£21M–£23M**, with **£11M–£12M** paid directly by Plymouth Argyle, **£7.27M** in grants via the Argyle Community Trust, and **£2.75M** from Plymouth City Council.
   * *Sources:* [Plymouth City Council — Brickfields Part I Briefing Paper (PDF)](https://democracy.plymouth.gov.uk/documents/s136778/Brickfields%20Part%20I%20briefing%20paper.pdf) · [BBC Sport — £21m Brickfields plans unveiled](https://www.bbc.co.uk/sport/football/64811721) · [BBC Sport — Foulston Park](https://www.bbc.com/sport/football/articles/clyvreqxxk5o)
5. **Bristol City — Robins High Performance Centre (`4.0★` Training `16` / `3.5★` Youth `15`, £18M–£20M):**
   * **Bristol City FC (2021):** A 4,000m² Category 1-capable facility in Failand (North Somerset) housing the First Team and Academy under one roof. Includes hydrotherapy, cryotherapy, altitude training, medical/rehab suites, gym, tactics room, a 500-seat floodlit show pitch, and two additional full-size grass pitches. Total cost: **£18M–£20M**.
   * *Sources:* [KKA Architects — Robins High Performance Centre (£18M budget)](https://kka.studio/project/robins-hpc) · [Bristol Post — Steve Lansdown opens £20m Robins HPC](https://www.bristolpost.co.uk/sport/football/football-news/steve-lansdowns-speech-full-bristol-5658528)
6. **AFC Bournemouth — Canford Magna Performance Centre (`5.0★` Training `20` / `5.0★` Youth `20`, £32.0M + £3.75M land):**
   * **AFC Bournemouth (2024/25):** Built on the 57-acre former Canford Magna Golf Club (purchased for **£3.75M**), featuring 10 full-size outdoor pitches, 3 junior pitches, a full-size indoor dome, solar array, and Premier League elite medical, fitness, and sports science suites. Audited capital expenditure in Bournemouth's FY24 accounts: **£27.9M** spent by June 2024 out of the **£32.0M** total build.
   * *Sources:* [BBC News — New £32m AFC Bournemouth training centre opens](https://www.bbc.com/news/articles/c934enewe32o) · [AFC Bournemouth FY24 Annual Report & Financial Statements (PDF)](https://images.gc.afcbournemouthservices.co.uk/4213e360-089e-11f0-96ca-3b5257f7e8db.pdf)
