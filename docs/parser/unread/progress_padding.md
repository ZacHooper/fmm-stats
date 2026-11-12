# Player progress → training

| | from | to | size |
|---|---|---|---|
| FMM22 | 52,721,064 | 53,479,282 | 758,218 B, all `00` and `ff` |
| FMM27 | 57,721,082 | 58,755,162 | 1,034,080 B, all `00` |

## Known

The same size on every save of a career (training sits exactly this far after the progress
pool on every Frem save), and no non-filler byte on any save measured.

## Next

Phase 4 of the plan: confirm it stays empty on a late-season save of each game, then mark it
padding in the save map so nobody spends time on it again.
