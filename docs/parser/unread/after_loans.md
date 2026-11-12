# Loans → transfer band

| | from | to | size |
|---|---|---|---|
| FMM22 | 34,276,977 | 35,438,751 | 1.16 MB |
| FMM27 | 36,500,230 | 38,003,552 | 1.50 MB, 00 44% / ff 18% / other 38%, nearly all real bytes |

Between the end of the [loan pool](../loans.md) and the transfer band's `[u32 65,000][count]`
([save file map](../savefile-map.md#the-transfer-band)).

## Known

Nothing decoded yet. It sits between two tables about transfers (loans before, the season's
bids after), so transfer-related state is the first guess: shortlists, scouting, contract
offers, interest.

## Next

1. Entropy profile (`scripts/audit/entropy_profile.py`) to see where records are.
2. Look for count frames and for tids: a u32 equal to a player's tid in rows of a fixed width,
   checked against the person table.
3. Diff the three Truro saves: what grows as the window goes on.

## Evidence that would help

Two saves either side of one transfer action (a shortlist add, a scout assignment, an offer).
