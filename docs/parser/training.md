# training  ([`fmparser/tables/training.py`](../../fmparser/tables/training.py))

Every player's training focus (role, position, attribute, intensity), plus a contract flag
and a squad-status byte. One fixed 61-byte row per person, `[count u32][rows]`, ~0.76 MB
after the [player_progress](player_progress.md) pool. The count is the person count, the
same as [person_info](person_info.md)'s (32,966 on Frem, 34,312 on Bucaspor), and row k
belongs to tid k.

## Layout

| offset | field | type | meaning | how we know |
|---|---|---|---|---|
| +0 | `tid` | u32 | equals the row index; `0xFFFFFFFF` = an unused row (1,973 on `frem-2030-06-22`) | |
| +4 | `uid` | u32 | | equals the person's uid |
| +8 | | u8 | unnamed | |
| +9, +13 | | 2 × u32 | unnamed (Adingra: 100,000 and 95,094) | |
| +17 | | u32 | unnamed; the module ties it to the Training page's green Progress bar (unverified) | |
| +21 | `intensity` | u16 | 2 normal; the module reads 3 as high (not seen on a screen here); 1 and 0 also occur | Adingra 2 = `Normal` |
| +23 | `focus_role` | u16 | Focus Role, a role id (`seeds/roles.csv`); `0xFFFF` on staff | Adingra 18 = `Poacher` |
| +25 | | u16 | 0 on a player, `0xFFFF` on staff | |
| +27 | `focus_attribute` | u16 | Focus Attribute, a code (`seeds/training_attributes.csv`) | Adingra 4 = `Shooting` |
| +29 | `focus_band`, `focus_column` | 2 × u8 | Focus Position, the pitch pair the match slots use (`core.primitives.pitch_position`) | Adingra 64, 2 = ST |
| +31 | | 6 B | unnamed: three u16 | |
| +37 | `contracted` | u8 | `0x87` on a player under contract; 0 on a free agent and on every member of staff | |
| +38 | | u8 | 0 on every row read | |
| +39 | `squad_status` | u8 | read only where `contracted` is set; see Quirks | 171 on the three players whose screens say `First Team` |
| +40 | | 21 B | unnamed; from +49, three `[day-of-year u16][year u16]` dates | |

## Evidence

`frem-2030-06-22`. Simon Adingra's Training Report; his row (tid 26552) at byte 54,923,658:

![Adingra, Training Report: Focus Role Poacher, Intensity Normal, Focus Attribute Shooting](img/training-1.png)

```
b8 67 00 00  5d dd 35 77  1d  a0 86 01 00  76 73 01 00  00 00 00 00
02 00  12 00  00 00  04 00  40 02  a4 00 ab 00 c3 00  87  00  ab  …
```

| on screen | raw bytes | parsed |
|---|---|---|
| Focus Role `Poacher` | +23 `12 00` | `focus_role` 18 = Poacher |
| Intensity `Normal` | +21 `02 00` | `intensity` 2 |
| Focus Attribute `Shooting` | +27 `04 00` | `focus_attribute` 4 |
| (his position, striker) | +29 `40 02` | `focus_position` ST |
| Squad Status `First Team` (Player Contract) | +37 `87`, +39 `ab` | `contracted`, `squad_status` 171 |

Lund Jensen and Ullits, whose profiles also say First Team, read 171 too. The Focus Role is the role a [player_lists](player_lists.md) entry carries:
Adingra's entry for this season reads role 18, Lund Jensen's 6 (Ball Playing Defender) and
Ullits' 1 (Sweeper Keeper), the roles their profiles show. Tested by
`tests/test_people_evidence.py`.

## Quirks

> **Quirk:** `squad_status` is not a loan flag. Frem's seven players out on loan (marked
> unavailable on the reserves' Contract screen and flagged in [player_progress](player_progress.md))
> read 164 on six rows and 171 on Mike Kieffer, the same 171 as First Team. On
> `bucaspor-2022-06-19` six loaned-out reserves read 65 (`LOAN_STATUS`, tested by
> `tests/test_ground_truth.py`), but the code does not carry across saves. Loans come from
> [player_progress](player_progress.md); only 171 = First Team is checked against a screen.

> **Quirk:** `focus_attribute` 4 is Shooting, and `seeds/training_attributes.csv` doesn't
> name code 4 (1,725 players on this save train it). Open in TODO under "Training table: the unread bytes
> and codes".

> **Decision:** staff rows (no Focus Role) and unused rows are dropped by `scrape_training`;
> every player's row is kept, our squad's or not.

## Output

`output/<label>/training.json`: one row per player in tid order (`tid, intensity,
focus_role, focus_attribute, focus_position, contracted, squad_status`), loaded into
`raw.training`.
